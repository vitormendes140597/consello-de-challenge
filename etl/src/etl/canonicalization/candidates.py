"""Canonical candidate generation and catalog similarity search."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Protocol

from openai import OpenAI

from etl.canonicalization.schemas import (
    CanonicalCandidate,
    CanonicalCandidateProjection,
    CanonicalCatalog,
    CanonicalCatalogEntry,
    CanonicalCatalogField,
    CanonicalItemCandidates,
)
from etl.common.fields import CANONICAL_FIELDS
from etl.common.schemas import (
    AlertMetadata,
)

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_TOP_K_CANDIDATES = 5
_NON_ALPHANUMERIC_PATTERN = re.compile(r"[^a-z0-9]+")
_ACRONYM_STOPWORDS = {"and", "in", "of", "on", "the", "for", "to", "with"}


class TextEmbeddingClient(Protocol):
    """Client capable of embedding batches of text."""

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of text strings.

        Args:
            texts (Sequence[str]): Non-empty text strings to embed.

        Returns:
            list[list[float]]: Embedding vectors in the same order as ``texts``.
        """


class OpenAITextEmbeddingClient:
    """OpenAI embedding client for canonical catalog similarity search.

    This client performs network calls to the OpenAI embeddings API.
    """

    def __init__(
        self,
        model: str = DEFAULT_EMBEDDING_MODEL,
        client: OpenAI | None = None,
    ) -> None:
        """Create an OpenAI embedding client.

        Args:
            model (str): Embedding model name to use.
            client (OpenAI | None): Optional preconfigured OpenAI SDK client.
                A default client is created when omitted.
        """

        self.model = model
        self._client = client or OpenAI()

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed text strings using the configured OpenAI model.

        Args:
            texts (Sequence[str]): Non-empty text strings to embed.

        Returns:
            list[list[float]]: Embedding vectors in input order.

        Raises:
            openai.OpenAIError: If the embeddings API request fails.
        """

        response = self._client.embeddings.create(
            model=self.model,
            input=list(texts),
        )
        return [
            list(item.embedding)
            for item in sorted(response.data, key=lambda item: item.index)
        ]


@dataclass(frozen=True)
class CatalogEmbeddingRecord:
    """Embedded representation of one canonical catalog entry.

    Attributes:
        field (str): Supported canonical field containing the entry.
        canonical_id (str): Stable catalog ID represented by the embedding.
        text (str): Text that was embedded for similarity search.
        embedding (tuple[float, ...]): Embedding vector for ``text``.
    """

    field: str
    canonical_id: str
    text: str
    embedding: tuple[float, ...]


@dataclass(frozen=True)
class CatalogEmbeddingIndex:
    """In-process embedding index for field-scoped catalog search.

    Attributes:
        catalog_version (int): Catalog version used to build the index.
        catalog_hash (str): Stable hash of catalog contents used for cache
            invalidation.
        embedding_model (str): Embedding model used to create records.
        records (tuple[CatalogEmbeddingRecord, ...]): Embedded catalog entries.
    """

    catalog_version: int
    catalog_hash: str
    embedding_model: str
    records: tuple[CatalogEmbeddingRecord, ...]

    @classmethod
    def build(
        cls,
        catalog: CanonicalCatalog,
        embedding_client: TextEmbeddingClient,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    ) -> CatalogEmbeddingIndex:
        """Build a field-scoped catalog embedding index.

        Args:
            catalog (CanonicalCatalog): Catalog to index.
            embedding_client (TextEmbeddingClient): Client used to embed catalog
                entry text. This may perform network calls depending on the
                client implementation.
            embedding_model (str): Embedding model name represented by the
                index.

        Returns:
            CatalogEmbeddingIndex: Versioned in-memory embedding index.
        """

        catalog_items: list[tuple[str, str, str]] = []
        for canonical_field in CANONICAL_FIELDS:
            catalog_field = catalog.fields[canonical_field]
            for canonical_id, entry in catalog_field.values.items():
                catalog_items.append(
                    (
                        canonical_field,
                        canonical_id,
                        build_catalog_entry_text(
                            field=canonical_field,
                            canonical_id=canonical_id,
                            catalog_field=catalog_field,
                            entry=entry,
                        ),
                    )
                )

        embeddings = embedding_client.embed_texts([item[2] for item in catalog_items])
        records = tuple(
            CatalogEmbeddingRecord(
                field=field,
                canonical_id=canonical_id,
                text=text,
                embedding=tuple(embedding),
            )
            for (field, canonical_id, text), embedding in zip(
                catalog_items,
                embeddings,
                strict=True,
            )
        )
        return cls(
            catalog_version=catalog.version,
            catalog_hash=catalog_content_hash(catalog),
            embedding_model=embedding_model,
            records=records,
        )

    @classmethod
    def load(cls, path: Path | str) -> CatalogEmbeddingIndex:
        """Load a persisted catalog embedding index from JSON.

        Args:
            path (Path | str): Local JSON index path.

        Returns:
            CatalogEmbeddingIndex: Parsed embedding index.

        Raises:
            OSError: If the index file cannot be read.
            json.JSONDecodeError: If the index file is not valid JSON.
            ValueError: If the decoded index has an invalid structure.
        """

        with Path(path).open(encoding="utf-8") as index_file:
            data = json.load(index_file)
        if not isinstance(data, dict):
            raise ValueError(f"Catalog embedding index must be a JSON object: {path}")
        return cls.from_json_data(data)

    @classmethod
    def load_or_build(
        cls,
        catalog: CanonicalCatalog,
        embedding_client: TextEmbeddingClient,
        path: Path | str,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    ) -> CatalogEmbeddingIndex:
        """Load a compatible local index or build and persist a new one.

        Args:
            catalog (CanonicalCatalog): Catalog represented by the index.
            embedding_client (TextEmbeddingClient): Client used when a new
                index must be built.
            path (Path | str): Local JSON index path.
            embedding_model (str): Embedding model name represented by the
                index.

        Returns:
            CatalogEmbeddingIndex: Compatible embedding index for ``catalog``.

        Raises:
            OSError: If an existing index cannot be read or a rebuilt index
                cannot be written.
            json.JSONDecodeError: If an existing index file is malformed JSON.
            ValueError: If an existing index has invalid structure.
        """

        index_path = Path(path)
        if index_path.exists():
            existing_index = cls.load(index_path)
            if existing_index.is_compatible_with(
                catalog=catalog,
                embedding_model=embedding_model,
            ):
                return existing_index

        index = cls.build(
            catalog=catalog,
            embedding_client=embedding_client,
            embedding_model=embedding_model,
        )
        index.save(index_path)
        return index

    @classmethod
    def from_json_data(cls, data: dict[str, object]) -> CatalogEmbeddingIndex:
        """Parse a catalog embedding index from decoded JSON data.

        Args:
            data (dict[str, object]): Decoded JSON object.

        Returns:
            CatalogEmbeddingIndex: Parsed embedding index.

        Raises:
            ValueError: If required fields or record values are malformed.
        """

        catalog_version = _require_int(data, "catalog_version")
        catalog_hash = _require_str(data, "catalog_hash")
        embedding_model = _require_str(data, "embedding_model")
        raw_records = data.get("records")
        if not isinstance(raw_records, list):
            raise ValueError("Catalog embedding index records must be a list")

        records = tuple(_embedding_record_from_json(record) for record in raw_records)
        return cls(
            catalog_version=catalog_version,
            catalog_hash=catalog_hash,
            embedding_model=embedding_model,
            records=records,
        )

    def save(self, path: Path | str) -> None:
        """Persist the catalog embedding index to a local JSON file.

        Args:
            path (Path | str): Output JSON index path.

        Returns:
            None: The index file is written atomically.

        Raises:
            OSError: If the output directory cannot be created or the file
                cannot be written.
            TypeError: If the index data is not JSON serializable.
        """

        index_path = Path(path)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = index_path.with_name(f".{index_path.name}.tmp")
        with temp_path.open("w", encoding="utf-8") as index_file:
            json.dump(self.to_json_data(), index_file, indent=2)
            index_file.write("\n")
        temp_path.replace(index_path)

    def to_json_data(self) -> dict[str, object]:
        """Serialize the catalog embedding index to JSON-compatible data.

        Returns:
            dict[str, object]: JSON-compatible index data.
        """

        return {
            "catalog_version": self.catalog_version,
            "catalog_hash": self.catalog_hash,
            "embedding_model": self.embedding_model,
            "records": [
                {
                    "field": record.field,
                    "canonical_id": record.canonical_id,
                    "text": record.text,
                    "embedding": list(record.embedding),
                }
                for record in self.records
            ],
        }

    def is_compatible_with(
        self,
        catalog: CanonicalCatalog,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    ) -> bool:
        """Return whether this index matches a catalog and embedding model.

        Args:
            catalog (CanonicalCatalog): Catalog to compare against.
            embedding_model (str): Embedding model name expected by the caller.

        Returns:
            bool: ``True`` when version, content hash, and embedding model match.
        """

        return (
            self.catalog_version == catalog.version
            and self.catalog_hash == catalog_content_hash(catalog)
            and self.embedding_model == embedding_model
        )

    def search(
        self,
        field: str,
        query_embedding: Sequence[float],
        top_k: int = DEFAULT_TOP_K_CANDIDATES,
    ) -> list[tuple[str, float]]:
        """Search candidate IDs within one canonical field.

        Args:
            field (str): Supported canonical field to search.
            query_embedding (Sequence[float]): Embedding vector for the source
                value.
            top_k (int): Maximum number of ranked candidate IDs to return.

        Returns:
            list[tuple[str, float]]: Candidate IDs and cosine similarity scores
            ordered from strongest to weakest.
        """

        scored: list[tuple[str, float]] = []
        for record in self.records:
            if record.field != field:
                continue
            score = _cosine_similarity(query_embedding, record.embedding)
            scored.append((record.canonical_id, score))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_k]


@dataclass
class CandidateGenerationCache:
    """In-memory candidate cache scoped to a catalog version and content hash."""

    catalog_version: int
    catalog_hash: str
    _candidates_by_key: dict[str, tuple[CanonicalCandidate, ...]] = dataclass_field(
        default_factory=dict
    )

    def get(
        self,
        field: str,
        normalized_name: str,
    ) -> tuple[CanonicalCandidate, ...] | None:
        """Return cached candidates for a normalized field value.

        Args:
            field (str): Supported canonical field name.
            normalized_name (str): Normalized extracted item name.

        Returns:
            tuple[CanonicalCandidate, ...] | None: Cached candidates or
            ``None`` when not cached.
        """

        return self._candidates_by_key.get(self._key(field, normalized_name))

    def set(
        self,
        field: str,
        normalized_name: str,
        candidates: Iterable[CanonicalCandidate],
    ) -> None:
        """Store candidates for a normalized field value.

        Args:
            field (str): Supported canonical field name.
            normalized_name (str): Normalized extracted item name.
            candidates (Iterable[CanonicalCandidate]): Candidates to cache.

        Returns:
            None: The cache is updated in place.
        """

        self._candidates_by_key[self._key(field, normalized_name)] = tuple(candidates)

    def _key(self, field: str, normalized_name: str) -> str:
        """Build one cache key including catalog identity.

        Args:
            field (str): Supported canonical field name.
            normalized_name (str): Normalized extracted item name.

        Returns:
            str: Stable cache key for the field value.
        """

        return f"{self.catalog_version}:{self.catalog_hash}:{field}:{normalized_name}"


class CanonicalCandidateGenerator:
    """Generate deterministic and embedding-backed canonical candidates."""

    def __init__(
        self,
        catalog: CanonicalCatalog,
        embedding_client: TextEmbeddingClient | None = None,
        embedding_index: CatalogEmbeddingIndex | None = None,
        embedding_index_path: Path | str | None = None,
        top_k: int = DEFAULT_TOP_K_CANDIDATES,
        cache: CandidateGenerationCache | None = None,
    ) -> None:
        """Create a canonical candidate generator.

        Args:
            catalog (CanonicalCatalog): Canonical catalog used for candidates.
            embedding_client (TextEmbeddingClient | None): Optional client used
                to embed source values and build an index.
            embedding_index (CatalogEmbeddingIndex | None): Optional prebuilt
                embedding index for catalog search.
            embedding_index_path (Path | str | None): Optional local JSON path
                used to load or persist a versioned catalog embedding index.
            top_k (int): Maximum number of embedding candidates per item.
            cache (CandidateGenerationCache | None): Optional candidate cache.
        """

        self.catalog = catalog
        self.embedding_client = embedding_client
        self.embedding_index = embedding_index
        self.embedding_index_path = (
            Path(embedding_index_path) if embedding_index_path is not None else None
        )
        self.top_k = top_k
        self.catalog_hash = catalog_content_hash(catalog)
        self.cache = cache or CandidateGenerationCache(
            catalog_version=catalog.version,
            catalog_hash=self.catalog_hash,
        )

    def project_metadata(
        self,
        metadata: AlertMetadata,
    ) -> CanonicalCandidateProjection:
        """Generate candidates for all canonicalizable items in metadata.

        Args:
            metadata (AlertMetadata): First-pass source metadata.

        Returns:
            CanonicalCandidateProjection: Candidate sets for each source item.
        """

        projected_items: list[CanonicalItemCandidates] = []
        for canonical_field in CANONICAL_FIELDS:
            for item_index, item in enumerate(getattr(metadata, canonical_field)):
                name = item.name
                normalized_name = normalize_catalog_text(name)
                projected_items.append(
                    CanonicalItemCandidates(
                        field=canonical_field,
                        item_index=item_index,
                        name=name,
                        normalized_name=normalized_name,
                        candidates=list(
                            self._candidates_for_value(
                                canonical_field,
                                normalized_name,
                            )
                        ),
                    )
                )

        return CanonicalCandidateProjection(
            catalog_version=self.catalog.version,
            catalog_hash=self.catalog_hash,
            items=projected_items,
        )

    def _candidates_for_value(
        self,
        field: str,
        normalized_name: str,
    ) -> tuple[CanonicalCandidate, ...]:
        """Generate candidates for one normalized value.

        Args:
            field (str): Supported canonical field.
            normalized_name (str): Normalized item name.

        Returns:
            tuple[CanonicalCandidate, ...]: Ordered candidate list.
        """

        cached_candidates = self.cache.get(field, normalized_name)
        if cached_candidates is not None:
            return cached_candidates

        deterministic_candidates = self._deterministic_candidates(
            field=field,
            normalized_name=normalized_name,
        )
        if len(deterministic_candidates) == 1:
            candidates = tuple(deterministic_candidates)
            self.cache.set(field, normalized_name, candidates)
            return candidates

        embedding_candidates = self._embedding_candidates(
            field=field,
            normalized_name=normalized_name,
            existing_ids={
                candidate.canonical_id for candidate in deterministic_candidates
            },
        )
        candidates = tuple([*deterministic_candidates, *embedding_candidates])
        self.cache.set(field, normalized_name, candidates)
        return candidates

    def _deterministic_candidates(
        self,
        field: str,
        normalized_name: str,
    ) -> list[CanonicalCandidate]:
        """Return exact deterministic candidates for one field value.

        Args:
            field (str): Supported canonical field.
            normalized_name (str): Normalized item name.

        Returns:
            list[CanonicalCandidate]: Strong exact candidates in catalog order.
        """

        candidates: list[CanonicalCandidate] = []
        catalog_field = self.catalog.fields[field]
        for canonical_id, entry in catalog_field.values.items():
            if _matches_exclusion(normalized_name, entry.exclude):
                continue
            match_source = _deterministic_match_source(
                field=field,
                canonical_id=canonical_id,
                entry=entry,
                normalized_name=normalized_name,
            )
            if match_source is None:
                continue
            candidates.append(
                _candidate_from_entry(
                    canonical_id=canonical_id,
                    entry=entry,
                    match_source=match_source,
                    score=None,
                )
            )
        return candidates

    def _embedding_candidates(
        self,
        field: str,
        normalized_name: str,
        existing_ids: set[str],
    ) -> list[CanonicalCandidate]:
        """Return field-scoped embedding candidates for one value.

        Args:
            field (str): Supported canonical field.
            normalized_name (str): Normalized item name.
            existing_ids (set[str]): Candidate IDs already returned through
                deterministic matching.

        Returns:
            list[CanonicalCandidate]: Similarity-ranked candidates not already
            present in ``existing_ids``.
        """

        if self.embedding_client is None:
            return []

        embedding_index = self._embedding_index()
        query_embedding = self.embedding_client.embed_texts([normalized_name])[0]
        candidates: list[CanonicalCandidate] = []
        for canonical_id, score in embedding_index.search(
            field=field,
            query_embedding=query_embedding,
            top_k=self.top_k,
        ):
            if canonical_id in existing_ids:
                continue
            entry = self.catalog.fields[field].values[canonical_id]
            if _matches_exclusion(normalized_name, entry.exclude):
                continue
            candidates.append(
                _candidate_from_entry(
                    canonical_id=canonical_id,
                    entry=entry,
                    match_source="embedding_similarity",
                    score=score,
                )
            )
        return candidates

    def _embedding_index(self) -> CatalogEmbeddingIndex:
        """Return a compatible embedding index, building one when needed.

        Returns:
            CatalogEmbeddingIndex: Index for this generator's catalog.

        Raises:
            ValueError: If embedding search is requested without an embedding
                client.
        """

        if (
            self.embedding_index is not None
            and self.embedding_index.catalog_version == self.catalog.version
            and self.embedding_index.catalog_hash == self.catalog_hash
        ):
            return self.embedding_index

        if self.embedding_client is None:
            raise ValueError("Embedding client is required to build catalog index")

        if self.embedding_index_path is not None:
            self.embedding_index = CatalogEmbeddingIndex.load_or_build(
                catalog=self.catalog,
                embedding_client=self.embedding_client,
                path=self.embedding_index_path,
            )
            return self.embedding_index

        self.embedding_index = CatalogEmbeddingIndex.build(
            catalog=self.catalog,
            embedding_client=self.embedding_client,
        )
        return self.embedding_index


def catalog_content_hash(catalog: CanonicalCatalog) -> str:
    """Return a stable hash for canonical catalog contents.

    Args:
        catalog (CanonicalCatalog): Catalog to hash.

    Returns:
        str: SHA-256 hash of the catalog JSON representation.
    """

    catalog_json = json.dumps(
        catalog.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(catalog_json.encode("utf-8")).hexdigest()


def build_catalog_entry_text(
    field: str,
    canonical_id: str,
    catalog_field: CanonicalCatalogField,
    entry: CanonicalCatalogEntry,
) -> str:
    """Build embedding text for one canonical catalog entry.

    Args:
        field (str): Supported canonical field containing the entry.
        canonical_id (str): Stable canonical ID.
        catalog_field (CanonicalCatalogField): Field-level catalog definition.
        entry (CanonicalCatalogEntry): Entry-level catalog definition.

    Returns:
        str: Text representation used for catalog embedding.
    """

    parts = [
        f"field: {field}",
        f"field description: {catalog_field.description}",
        f"canonical id: {canonical_id}",
        f"label: {entry.label}",
        f"description: {entry.description}",
    ]
    if entry.aliases:
        parts.append("aliases: " + ", ".join(entry.aliases))
    if entry.related_terms:
        parts.append("related terms: " + ", ".join(entry.related_terms))
    if entry.law_or_regime_aliases:
        parts.append(
            "explicit law or regime aliases: " + ", ".join(entry.law_or_regime_aliases)
        )
    if entry.exclude:
        parts.append("exclude: " + ", ".join(entry.exclude))
    return "\n".join(parts)


def normalize_catalog_text(value: str) -> str:
    """Normalize catalog and source text for exact matching.

    Args:
        value (str): Raw text to normalize.

    Returns:
        str: Lower-case alphanumeric text with normalized whitespace.
    """

    normalized = _NON_ALPHANUMERIC_PATTERN.sub(" ", value.casefold())
    return " ".join(normalized.split())


def _candidate_from_entry(
    canonical_id: str,
    entry: CanonicalCatalogEntry,
    match_source: str,
    score: float | None,
) -> CanonicalCandidate:
    """Create a candidate schema from one catalog entry."""

    return CanonicalCandidate(
        canonical_id=canonical_id,
        label=entry.label,
        match_source=match_source,
        score=score,
        description=entry.description,
        aliases=entry.aliases,
        related_terms=entry.related_terms,
        exclude=entry.exclude,
    )


def _deterministic_match_source(
    field: str,
    canonical_id: str,
    entry: CanonicalCatalogEntry,
    normalized_name: str,
) -> str | None:
    """Return the deterministic match source for a normalized value."""

    if normalized_name == normalize_catalog_text(canonical_id):
        return "canonical_id"
    if normalized_name == normalize_catalog_text(entry.label):
        return "label"
    if normalized_name in {normalize_catalog_text(alias) for alias in entry.aliases}:
        return "alias"
    if normalized_name == _catalog_acronym(entry.label):
        return "acronym"
    if field == "regulators" and normalized_name in {
        normalize_catalog_text(alias) for alias in entry.law_or_regime_aliases
    }:
        return "law_or_regime_alias"
    return None


def _catalog_acronym(value: str) -> str:
    """Build a simple acronym from a catalog label or phrase."""

    words = [
        word
        for word in normalize_catalog_text(value).split()
        if word not in _ACRONYM_STOPWORDS
    ]
    if len(words) <= 1:
        return normalize_catalog_text(value)
    return "".join(word[0] for word in words)


def _matches_exclusion(normalized_name: str, exclusions: Sequence[str]) -> bool:
    """Return whether a normalized value is explicitly excluded."""

    return normalized_name in {normalize_catalog_text(value) for value in exclusions}


def _embedding_record_from_json(record: object) -> CatalogEmbeddingRecord:
    """Parse one persisted embedding record."""

    if not isinstance(record, dict):
        raise ValueError("Catalog embedding index records must be JSON objects")

    raw_embedding = record.get("embedding")
    if not isinstance(raw_embedding, list):
        raise ValueError("Catalog embedding record embedding must be a list")

    embedding: list[float] = []
    for value in raw_embedding:
        if not isinstance(value, int | float):
            raise ValueError("Catalog embedding values must be numeric")
        embedding.append(float(value))

    return CatalogEmbeddingRecord(
        field=_require_str(record, "field"),
        canonical_id=_require_str(record, "canonical_id"),
        text=_require_str(record, "text"),
        embedding=tuple(embedding),
    )


def _require_int(data: dict[str, object], key: str) -> int:
    """Return a required integer value from decoded JSON data."""

    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"Catalog embedding index {key} must be an integer")
    return value


def _require_str(data: dict[str, object], key: str) -> str:
    """Return a required string value from decoded JSON data."""

    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Catalog embedding index {key} must be a string")
    return value


def _cosine_similarity(
    left: Sequence[float],
    right: Sequence[float],
) -> float:
    """Compute cosine similarity for two embedding vectors."""

    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


__all__ = [
    "DEFAULT_EMBEDDING_MODEL",
    "DEFAULT_TOP_K_CANDIDATES",
    "CandidateGenerationCache",
    "CanonicalCandidateGenerator",
    "CatalogEmbeddingIndex",
    "CatalogEmbeddingRecord",
    "OpenAITextEmbeddingClient",
    "TextEmbeddingClient",
    "build_catalog_entry_text",
    "catalog_content_hash",
    "normalize_catalog_text",
]

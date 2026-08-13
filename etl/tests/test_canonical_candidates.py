"""Tests for canonical candidate generation."""

from __future__ import annotations

import copy

from etl.canonicalization.candidates import (
    CanonicalCandidateGenerator,
    CatalogEmbeddingIndex,
    CatalogEmbeddingRecord,
    build_catalog_entry_text,
    catalog_content_hash,
)
from etl.canonicalization.schemas import CanonicalCatalog
from etl.common.fields import CANONICAL_FIELDS
from etl.common.schemas import AlertMetadata


def test_exact_alias_returns_deterministic_candidate_without_embedding() -> None:
    """Verify strong aliases bypass embedding fallback."""

    catalog = _catalog(
        overrides={
            "companies": {
                "solstice_robotics": {
                    "label": "Solstice Robotics",
                    "aliases": ["SLRB"],
                    "description": "Tracked robotics company.",
                }
            }
        }
    )
    embedding_client = FakeEmbeddingClient(vector=[1.0, 0.0])
    generator = CanonicalCandidateGenerator(
        catalog=catalog,
        embedding_client=embedding_client,
    )

    projection = generator.project_metadata(
        AlertMetadata(
            companies=[
                {
                    "name": "SLRB",
                    "ticker": "SLRB",
                    "rationale": "Ticker appears in the source.",
                }
            ]
        )
    )

    item = projection.items[0]
    assert [candidate.canonical_id for candidate in item.candidates] == [
        "solstice_robotics"
    ]
    assert item.candidates[0].match_source == "alias"
    assert embedding_client.calls == []


def test_exact_id_label_and_acronym_return_deterministic_candidates() -> None:
    """Verify deterministic matching covers IDs, labels, and acronyms."""

    catalog = _catalog(
        overrides={
            "regulators": {
                "us_investment_committee": {
                    "label": "Committee on Foreign Investment in the United States",
                    "aliases": [],
                    "description": "US investment review committee.",
                },
                "federal_reserve": {
                    "label": "Board of Governors",
                    "aliases": [],
                    "description": "US central bank.",
                },
            }
        }
    )
    generator = CanonicalCandidateGenerator(catalog=catalog)

    projection = generator.project_metadata(
        AlertMetadata(
            regulators=[
                {
                    "name": "federal_reserve",
                    "rationale": "Canonical id appears in source.",
                },
                {
                    "name": "Board of Governors",
                    "rationale": "Full label appears in source.",
                },
                {
                    "name": "CFIUS",
                    "rationale": "Acronym appears in source.",
                },
            ]
        )
    )

    assert [item.candidates[0].match_source for item in projection.items] == [
        "canonical_id",
        "label",
        "acronym",
    ]
    assert [item.candidates[0].canonical_id for item in projection.items] == [
        "federal_reserve",
        "federal_reserve",
        "us_investment_committee",
    ]


def test_regulator_law_alias_returns_explicit_entity_candidate() -> None:
    """Verify regulator law aliases map only through explicit catalog entries."""

    catalog = _catalog(
        overrides={
            "regulators": {
                "european_commission": {
                    "label": "European Commission",
                    "law_or_regime_aliases": ["EU AI Act"],
                    "description": "EU executive body.",
                }
            }
        }
    )
    generator = CanonicalCandidateGenerator(catalog=catalog)

    projection = generator.project_metadata(
        AlertMetadata(
            regulators=[
                {
                    "name": "EU AI Act",
                    "rationale": "The source names the EU AI Act.",
                }
            ]
        )
    )

    assert projection.items[0].candidates[0].canonical_id == "european_commission"
    assert projection.items[0].candidates[0].match_source == "law_or_regime_alias"


def test_exclusion_blocks_deterministic_candidate() -> None:
    """Verify explicit exclusions prevent nearby deterministic matches."""

    catalog = _catalog(
        overrides={
            "regulators": {
                "cfius": {
                    "label": "CFIUS",
                    "aliases": ["US Department of Commerce"],
                    "exclude": ["US Department of Commerce"],
                    "description": "US investment review committee.",
                }
            }
        }
    )
    generator = CanonicalCandidateGenerator(catalog=catalog)

    projection = generator.project_metadata(
        AlertMetadata(
            regulators=[
                {
                    "name": "US Department of Commerce",
                    "rationale": "The source names Commerce.",
                }
            ]
        )
    )

    assert projection.items[0].candidates == []


def test_embedding_search_is_field_scoped() -> None:
    """Verify embedding fallback searches only the item's canonical field."""

    catalog = _catalog(
        overrides={
            "sectors": {
                "industrial_robotics": {
                    "label": "Industrial Robotics",
                    "description": "Robotics sector.",
                }
            },
            "key_markets": {
                "warehouse_automation": {
                    "label": "Warehouse Automation",
                    "description": "Warehouse automation demand market.",
                }
            },
        }
    )
    index = CatalogEmbeddingIndex(
        catalog_version=catalog.version,
        catalog_hash=catalog_content_hash(catalog),
        embedding_model="text-embedding-3-small",
        records=(
            CatalogEmbeddingRecord(
                field="sectors",
                canonical_id="industrial_robotics",
                text="industrial robotics",
                embedding=(1.0, 0.0),
            ),
            CatalogEmbeddingRecord(
                field="key_markets",
                canonical_id="warehouse_automation",
                text="warehouse automation",
                embedding=(1.0, 0.0),
            ),
        ),
    )
    embedding_client = FakeEmbeddingClient(vector=[1.0, 0.0])
    generator = CanonicalCandidateGenerator(
        catalog=catalog,
        embedding_client=embedding_client,
        embedding_index=index,
    )

    projection = generator.project_metadata(
        AlertMetadata(
            key_markets=[
                {
                    "name": "automated warehouse systems",
                    "rationale": "The source cites warehouse systems.",
                }
            ]
        )
    )

    assert [candidate.canonical_id for candidate in projection.items[0].candidates] == [
        "warehouse_automation"
    ]


def test_candidate_generation_cache_reuses_normalized_source_value() -> None:
    """Verify repeated source values reuse cached candidates."""

    catalog = _catalog()
    index = CatalogEmbeddingIndex(
        catalog_version=catalog.version,
        catalog_hash=catalog_content_hash(catalog),
        embedding_model="text-embedding-3-small",
        records=(
            CatalogEmbeddingRecord(
                field="themes",
                canonical_id="themes_value",
                text="themes value",
                embedding=(1.0, 0.0),
            ),
        ),
    )
    embedding_client = FakeEmbeddingClient(vector=[1.0, 0.0])
    generator = CanonicalCandidateGenerator(
        catalog=catalog,
        embedding_client=embedding_client,
        embedding_index=index,
    )
    metadata = AlertMetadata(
        themes=[
            {
                "name": "capacity pressure",
                "rationale": "The source cites capacity pressure.",
            }
        ]
    )

    generator.project_metadata(metadata)
    generator.project_metadata(metadata)

    assert embedding_client.calls == [["capacity pressure"]]


def test_embedding_index_path_reuses_compatible_catalog_embeddings(tmp_path) -> None:
    """Verify compatible persisted indexes avoid re-embedding catalog entries."""

    catalog = _catalog()
    index_path = tmp_path / "canonical_embeddings.json"
    first_client = FakeEmbeddingClient(vector=[1.0, 0.0])
    first_generator = CanonicalCandidateGenerator(
        catalog=catalog,
        embedding_client=first_client,
        embedding_index_path=index_path,
    )
    metadata = AlertMetadata(
        themes=[
            {
                "name": "capacity pressure",
                "rationale": "The source cites capacity pressure.",
            }
        ]
    )

    first_generator.project_metadata(metadata)
    second_client = FakeEmbeddingClient(vector=[1.0, 0.0])
    second_generator = CanonicalCandidateGenerator(
        catalog=catalog,
        embedding_client=second_client,
        embedding_index_path=index_path,
    )
    second_generator.project_metadata(metadata)

    assert index_path.exists()
    assert len(first_client.calls) == 2
    assert first_client.calls[0] != ["capacity pressure"]
    assert second_client.calls == [["capacity pressure"]]


def test_embedding_index_path_rebuilds_stale_catalog_embeddings(tmp_path) -> None:
    """Verify stale persisted indexes are rebuilt for catalog content changes."""

    index_path = tmp_path / "canonical_embeddings.json"
    old_catalog = _catalog(
        overrides={
            "themes": {
                "old_theme": {
                    "label": "Old Theme",
                    "description": "Old theme boundary.",
                }
            }
        }
    )
    old_index = CatalogEmbeddingIndex.build(
        catalog=old_catalog,
        embedding_client=FakeEmbeddingClient(vector=[0.0, 1.0]),
    )
    old_index.save(index_path)
    new_catalog = _catalog(
        overrides={
            "themes": {
                "new_theme": {
                    "label": "New Theme",
                    "description": "New theme boundary.",
                }
            }
        }
    )
    embedding_client = FakeEmbeddingClient(vector=[1.0, 0.0])
    generator = CanonicalCandidateGenerator(
        catalog=new_catalog,
        embedding_client=embedding_client,
        embedding_index_path=index_path,
    )

    projection = generator.project_metadata(
        AlertMetadata(
            themes=[
                {
                    "name": "capacity pressure",
                    "rationale": "The source cites capacity pressure.",
                }
            ]
        )
    )
    loaded_index = CatalogEmbeddingIndex.load(index_path)

    assert [candidate.canonical_id for candidate in projection.items[0].candidates] == [
        "new_theme"
    ]
    assert loaded_index.catalog_hash == catalog_content_hash(new_catalog)
    assert len(embedding_client.calls) == 2


def test_catalog_entry_text_includes_mapping_hints() -> None:
    """Verify embedding text includes aliases, related terms, and exclusions."""

    catalog = _catalog(
        overrides={
            "regulators": {
                "cfius": {
                    "label": "CFIUS",
                    "aliases": ["Committee on Foreign Investment in the US"],
                    "related_terms": ["national security review"],
                    "law_or_regime_aliases": ["foreign investment review"],
                    "exclude": ["US Department of Commerce"],
                    "description": "US interagency committee.",
                }
            }
        }
    )
    field = catalog.fields["regulators"]
    entry = field.values["cfius"]

    text = build_catalog_entry_text(
        field="regulators",
        canonical_id="cfius",
        catalog_field=field,
        entry=entry,
    )

    assert "canonical id: cfius" in text
    assert "Committee on Foreign Investment" in text
    assert "national security review" in text
    assert "foreign investment review" in text
    assert "US Department of Commerce" in text


class FakeEmbeddingClient:
    """Fake embedding client used to avoid network calls."""

    def __init__(self, vector: list[float]) -> None:
        """Store the vector returned for every input text."""

        self.vector = vector
        self.calls: list[list[str]] = []

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Record texts and return the configured vector for each input."""

        self.calls.append(list(texts))
        return [self.vector for _ in texts]


def _catalog(
    overrides: dict[str, dict[str, dict[str, object]]] | None = None,
) -> CanonicalCatalog:
    """Create a minimal valid canonical catalog with optional field overrides.

    Args:
        overrides (dict[str, dict[str, dict[str, object]]] | None): Optional
            catalog entry overrides keyed by field and canonical ID.

    Returns:
        CanonicalCatalog: Valid test catalog.
    """

    fields: dict[str, object] = {}
    for field in CANONICAL_FIELDS:
        fields[field] = {
            "description": f"{field} field",
            "values": {
                f"{field}_value": {
                    "label": f"{field} value",
                    "aliases": [],
                    "related_terms": [],
                    "law_or_regime_aliases": [],
                    "exclude": [],
                    "description": f"{field} description",
                }
            },
        }

    for field, values in (overrides or {}).items():
        field_values = {}
        for canonical_id, entry in values.items():
            field_values[canonical_id] = {
                "aliases": [],
                "related_terms": [],
                "law_or_regime_aliases": [],
                "exclude": [],
                **entry,
            }
        fields[field] = {
            "description": f"{field} field",
            "values": copy.deepcopy(field_values),
        }

    return CanonicalCatalog.model_validate({"version": 1, "fields": fields})

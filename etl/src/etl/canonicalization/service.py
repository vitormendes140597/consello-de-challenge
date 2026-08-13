"""LLM canonicalization decision orchestration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from etl.canonicalization.candidates import CanonicalCandidateGenerator
from etl.canonicalization.prompts import build_canonicalization_prompt
from etl.canonicalization.schemas import (
    CanonicalCandidate,
    CanonicalCandidateProjection,
    CanonicalCatalog,
    CanonicalCompanyItem,
    CanonicalItemCandidates,
    CanonicalizationDecision,
    CanonicalizationPayload,
    CanonicalizedAlert,
    CanonicalizedMetadata,
    CanonicalMetadataItem,
)
from etl.common.fields import CANONICAL_FIELDS
from etl.common.schemas import AlertMetadata, EnrichedAlert


class StructuredCanonicalizationModel(Protocol):
    """Model runnable that returns structured canonicalization decisions."""

    def invoke(
        self,
        prompt: str,
    ) -> CanonicalizationDecision | Mapping[str, object]:
        """Invoke the model with one canonicalization prompt.

        Args:
            prompt (str): Model-facing canonicalization prompt.

        Returns:
            CanonicalizationDecision | Mapping[str, object]: Structured
            canonical decisions returned by the model.
        """


class CanonicalizationStructuredOutputModel(Protocol):
    """Chat model that can bind canonicalization structured output."""

    def with_structured_output(
        self,
        schema: type[CanonicalizationDecision],
    ) -> StructuredCanonicalizationModel:
        """Bind the model to the canonicalization decision schema.

        Args:
            schema (type[CanonicalizationDecision]): Pydantic schema defining
                canonical decision output.

        Returns:
            StructuredCanonicalizationModel: Runnable canonicalization decider.
        """


def build_canonicalization_decider(
    model: CanonicalizationStructuredOutputModel,
) -> StructuredCanonicalizationModel:
    """Bind a chat model to the canonicalization decision schema.

    Args:
        model (CanonicalizationStructuredOutputModel): Chat model supporting
            structured output binding.

    Returns:
        StructuredCanonicalizationModel: Runnable decider for canonicalization.
    """

    return model.with_structured_output(CanonicalizationDecision)


def canonicalize_alert(
    alert: EnrichedAlert,
    catalog: CanonicalCatalog,
    model: CanonicalizationStructuredOutputModel,
    candidate_generator: CanonicalCandidateGenerator,
) -> CanonicalizedAlert:
    """Canonicalize one complete enriched alert in one LLM decision request.

    Args:
        alert (EnrichedAlert): First-pass enriched alert to canonicalize.
        catalog (CanonicalCatalog): Canonical catalog used for validation.
        model (CanonicalizationStructuredOutputModel): Structured-output-capable
            model used for canonical decisions.
        candidate_generator (CanonicalCandidateGenerator): Local candidate
            generator for the source alert.

    Returns:
        CanonicalizedAlert: Source alert with original extracted items preserved
        and canonical IDs attached.

    Raises:
        ValueError: If the decision output changes item counts, returns values
            outside the projected candidate sets, or returns values outside the
            catalog.
        pydantic.ValidationError: If mapping responses do not validate as
            ``CanonicalizationDecision`` or canonicalized alert schemas.
    """

    metadata = AlertMetadata.model_validate(alert.model_dump())
    canonicalized_metadata = _canonicalize_metadata(
        source_metadata=metadata,
        source_payload=alert.model_dump(mode="json"),
        catalog=catalog,
        model=model,
        candidate_generator=candidate_generator,
    )
    return CanonicalizedAlert.model_validate(
        {
            "id": alert.id,
            "received_at": alert.received_at,
            "subject": alert.subject,
            "body": alert.body,
            **canonicalized_metadata.model_dump(mode="json"),
        }
    )


def canonicalize_payload(
    payload: CanonicalizationPayload,
    catalog: CanonicalCatalog,
    model: CanonicalizationStructuredOutputModel,
    candidate_generator: CanonicalCandidateGenerator,
) -> CanonicalizedMetadata:
    """Canonicalize one complete common canonicalization payload.

    Args:
        payload (CanonicalizationPayload): Common first-pass metadata payload,
            typically produced by a profile adapter in later processing.
        catalog (CanonicalCatalog): Canonical catalog used for validation.
        model (CanonicalizationStructuredOutputModel): Structured-output-capable
            model used for canonical decisions.
        candidate_generator (CanonicalCandidateGenerator): Local candidate
            generator for the payload.

    Returns:
        CanonicalizedMetadata: Canonicalized metadata arrays with source item
        values preserved.

    Raises:
        ValueError: If the decision output changes item counts, returns values
            outside the projected candidate sets, or returns values outside the
            catalog.
        pydantic.ValidationError: If mapping responses do not validate as
            ``CanonicalizationDecision`` or canonicalized metadata schemas.
    """

    source_metadata = AlertMetadata.model_validate(payload.model_dump())
    return _canonicalize_metadata(
        source_metadata=source_metadata,
        source_payload=payload.model_dump(mode="json"),
        catalog=catalog,
        model=model,
        candidate_generator=candidate_generator,
    )


def _canonicalize_metadata(
    source_metadata: AlertMetadata,
    source_payload: Mapping[str, object],
    catalog: CanonicalCatalog,
    model: CanonicalizationStructuredOutputModel,
    candidate_generator: CanonicalCandidateGenerator,
) -> CanonicalizedMetadata:
    """Canonicalize shared source metadata through one structured decision."""

    candidate_projection = candidate_generator.project_metadata(source_metadata)
    prompt = build_canonicalization_prompt(
        source_payload=source_payload,
        candidate_projection=candidate_projection,
    )
    result = build_canonicalization_decider(model).invoke(prompt)
    if isinstance(result, CanonicalizationDecision):
        decision = result
    else:
        decision = CanonicalizationDecision.model_validate(result)

    _validate_decision_lengths(source_metadata, decision)
    _validate_decision_candidates(decision, candidate_projection)
    canonicalized_metadata = _reconstruct_canonicalized_metadata(
        source_metadata=source_metadata,
        decision=decision,
    )
    canonicalized_metadata.validate_canonical_values(catalog)
    return canonicalized_metadata


def _validate_decision_lengths(
    source_metadata: AlertMetadata,
    decision: CanonicalizationDecision,
) -> None:
    """Validate decision arrays preserve source item counts."""

    for field in CANONICAL_FIELDS:
        source_count = len(getattr(source_metadata, field))
        decision_count = len(getattr(decision, field))
        if source_count == decision_count:
            continue
        raise ValueError(
            "Canonicalization decision changed item count for "
            f"{field!r}: expected {source_count}, got {decision_count}"
        )


def _validate_decision_candidates(
    decision: CanonicalizationDecision,
    candidate_projection: CanonicalCandidateProjection,
) -> None:
    """Validate non-null decisions are present in projected candidates."""

    for field in CANONICAL_FIELDS:
        for item_index, item_decision in enumerate(getattr(decision, field)):
            if item_decision.canonical is None:
                continue
            candidate_ids = candidate_projection.candidate_ids_for(
                field=field,
                item_index=item_index,
            )
            if item_decision.canonical in candidate_ids:
                _validate_regulator_law_candidate(
                    candidate_projection=candidate_projection,
                    field=field,
                    item_index=item_index,
                    canonical_id=item_decision.canonical,
                )
                continue
            raise ValueError(
                "Canonicalization decision returned a canonical ID outside "
                f"the projected candidates for {field}[{item_index}]: "
                f"{item_decision.canonical!r}"
            )


def _validate_regulator_law_candidate(
    candidate_projection: CanonicalCandidateProjection,
    field: str,
    item_index: int,
    canonical_id: str,
) -> None:
    """Reject regulator law/regime mappings without explicit catalog support."""

    if field != "regulators":
        return

    item_candidates = _projected_item_candidates(
        candidate_projection=candidate_projection,
        field=field,
        item_index=item_index,
    )
    if item_candidates is None or not _is_regulator_law_or_regime_reference(
        item_candidates.name
    ):
        return

    candidate = _candidate_by_id(item_candidates.candidates, canonical_id)
    if candidate is not None and candidate.match_source == "law_or_regime_alias":
        return

    raise ValueError(
        "Canonicalization decision mapped a regulator law, regime, review "
        "process, or framework without an explicit catalog law_or_regime_alias "
        f"for regulators[{item_index}]: {canonical_id!r}"
    )


def _projected_item_candidates(
    candidate_projection: CanonicalCandidateProjection,
    field: str,
    item_index: int,
) -> CanonicalItemCandidates | None:
    """Return projected candidates for one source item."""

    for item_candidates in candidate_projection.items:
        if item_candidates.field == field and item_candidates.item_index == item_index:
            return item_candidates
    return None


def _candidate_by_id(
    candidates: list[CanonicalCandidate],
    canonical_id: str,
) -> CanonicalCandidate | None:
    """Return one candidate by canonical ID."""

    for candidate in candidates:
        if candidate.canonical_id == canonical_id:
            return candidate
    return None


def _is_regulator_law_or_regime_reference(value: str) -> bool:
    """Return whether regulator source text names a law or regime concept."""

    normalized = value.casefold()
    markers = (
        " act",
        " law",
        " regulation",
        " rule",
        " regime",
        " review",
        " process",
        " framework",
        " enforcement",
        " directive",
        " guidance",
    )
    padded = f" {normalized} "
    return any(marker in padded for marker in markers)


def _reconstruct_canonicalized_metadata(
    source_metadata: AlertMetadata,
    decision: CanonicalizationDecision,
) -> CanonicalizedMetadata:
    """Attach canonical decisions to original source items."""

    metadata: dict[str, object] = {}
    for field in CANONICAL_FIELDS:
        metadata[field] = _reconstruct_field(
            source_items=getattr(source_metadata, field),
            decision_items=getattr(decision, field),
            is_company=field == "companies",
        )
    return CanonicalizedMetadata.model_validate(metadata)


def _reconstruct_field(
    source_items: list[object],
    decision_items: list[object],
    is_company: bool,
) -> list[CanonicalCompanyItem | CanonicalMetadataItem]:
    """Reconstruct one canonicalized field from source items and decisions."""

    reconstructed: list[CanonicalCompanyItem | CanonicalMetadataItem] = []
    for source_item, decision_item in zip(source_items, decision_items, strict=True):
        if is_company:
            reconstructed.append(
                CanonicalCompanyItem(
                    name=source_item.name,
                    ticker=source_item.ticker,
                    canonical=decision_item.canonical,
                    rationale=source_item.rationale,
                )
            )
            continue
        reconstructed.append(
            CanonicalMetadataItem(
                name=source_item.name,
                canonical=decision_item.canonical,
                rationale=source_item.rationale,
            )
        )
    return reconstructed


__all__ = [
    "CanonicalizationStructuredOutputModel",
    "StructuredCanonicalizationModel",
    "build_canonicalization_decider",
    "canonicalize_alert",
    "canonicalize_payload",
]

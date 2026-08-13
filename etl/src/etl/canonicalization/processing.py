"""Processing orchestration for alert and profile canonicalization."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from etl.canonicalization.candidates import CanonicalCandidateGenerator
from etl.canonicalization.schemas import (
    CanonicalCatalog,
    CanonicalizationPayload,
    CanonicalizedAlert,
    CanonicalizedCustomerProfile,
    CanonicalizedMetadata,
    CanonicalMetadataItem,
)
from etl.canonicalization.service import (
    CanonicalizationStructuredOutputModel,
    canonicalize_alert,
    canonicalize_payload,
)
from etl.common.fields import CANONICAL_FIELDS, METADATA_FIELDS
from etl.common.io import AlertDataLoader, JsonRecordStore, StorageBackend
from etl.common.schemas import EnrichedAlert

PROFILE_COMPANY_FIELDS = (
    "client_name",
    "focal_companies",
    "competitors",
    "suppliers",
    "customers",
    "companies",
)
PROFILE_OUTPUT_COMPANY_FIELDS = (
    "focal_companies",
    "competitors",
    "suppliers",
    "customers",
)
PROFILE_SECTOR_FIELDS = ("sector", "sectors")
PROFILE_OUTPUT_METADATA_FIELDS = (
    "geo_markets",
    "key_markets",
    "commodities",
    "regulators",
    "macro_sensitivities",
    "themes",
)


@dataclass(frozen=True)
class ProfileCanonicalizationInput:
    """Profile payload plus source-field provenance.

    Attributes:
        payload (CanonicalizationPayload): Common metadata payload sent through
            canonicalization.
        company_fields (tuple[str, ...]): Source profile field for each company
            item in payload order.
        metadata_fields (dict[str, tuple[str, ...]]): Source profile field for
            each non-company item, keyed by canonical metadata field.
    """

    payload: CanonicalizationPayload
    company_fields: tuple[str, ...]
    metadata_fields: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class CanonicalizationProcessingResult:
    """Validated canonicalization records produced by one processing run.

    Attributes:
        alerts (list[CanonicalizedAlert]): Canonicalized alerts from the
            enriched input dataset.
        customer_profile (CanonicalizedCustomerProfile): Canonicalized customer
            profile output.
    """

    alerts: list[CanonicalizedAlert]
    customer_profile: CanonicalizedCustomerProfile


def enriched_alert_to_payload(alert: EnrichedAlert) -> CanonicalizationPayload:
    """Adapt an enriched alert to the common canonicalization payload.

    Args:
        alert (EnrichedAlert): Enriched alert containing first-pass metadata.

    Returns:
        CanonicalizationPayload: Common metadata payload with alert trace fields.

    Raises:
        pydantic.ValidationError: If adapted data does not validate as the
            canonicalization payload schema.
    """

    return CanonicalizationPayload.model_validate(
        {
            "source_type": "alert",
            "source_id": alert.id,
            **_metadata_dump(alert),
        }
    )


def customer_profile_to_payload(
    profile: Mapping[str, object],
) -> CanonicalizationPayload:
    """Adapt a customer profile JSON object to canonicalization metadata.

    Args:
        profile (Mapping[str, object]): Decoded customer profile JSON object.

    Returns:
        CanonicalizationPayload: Common metadata payload containing profile
            companies, sector values, and supported metadata arrays.

    Raises:
        ValueError: If a mapped profile field has an unsupported shape.
        pydantic.ValidationError: If adapted data does not validate as the
            canonicalization payload schema.
    """

    return customer_profile_to_canonicalization_input(profile).payload


def customer_profile_to_canonicalization_input(
    profile: Mapping[str, object],
) -> ProfileCanonicalizationInput:
    """Adapt a customer profile with structural source-field provenance.

    Args:
        profile (Mapping[str, object]): Decoded customer profile JSON object.

    Returns:
        ProfileCanonicalizationInput: Common payload plus per-item source
        profile fields used to project canonical IDs back to profile shape.

    Raises:
        ValueError: If a mapped profile field has an unsupported shape.
        pydantic.ValidationError: If adapted data does not validate as the
            canonicalization payload schema.
    """

    company_items, company_fields = _profile_company_items(profile)
    metadata_fields: dict[str, tuple[str, ...]] = {}
    payload: dict[str, object] = {
        "source_type": "customer_profile",
        "source_id": _profile_source_id(profile),
        "companies": company_items,
    }

    for field in METADATA_FIELDS:
        if field == "sectors":
            items, source_fields = _profile_metadata_items(
                profile,
                PROFILE_SECTOR_FIELDS,
            )
            payload[field] = items
            metadata_fields[field] = source_fields
            continue
        items, source_fields = _profile_metadata_items(profile, (field,))
        payload[field] = items
        metadata_fields[field] = source_fields

    return ProfileCanonicalizationInput(
        payload=CanonicalizationPayload.model_validate(payload),
        company_fields=company_fields,
        metadata_fields=metadata_fields,
    )


def canonicalized_metadata_to_alert(
    alert: EnrichedAlert,
    metadata: CanonicalizedMetadata,
) -> CanonicalizedAlert:
    """Convert canonicalized metadata into a canonicalized alert record.

    Args:
        alert (EnrichedAlert): Source enriched alert whose source fields are
            preserved.
        metadata (CanonicalizedMetadata): Canonicalized metadata arrays.

    Returns:
        CanonicalizedAlert: Validated canonicalized alert output.

    Raises:
        pydantic.ValidationError: If the combined alert output is malformed.
    """

    return CanonicalizedAlert.model_validate(
        {
            "id": alert.id,
            "received_at": alert.received_at,
            "subject": alert.subject,
            "body": alert.body,
            **metadata.model_dump(mode="json"),
        }
    )


def canonicalized_metadata_to_customer_profile(
    profile: Mapping[str, object],
    metadata: CanonicalizedMetadata,
) -> CanonicalizedCustomerProfile:
    """Convert canonicalized metadata into customer-profile output.

    Args:
        profile (Mapping[str, object]): Original decoded customer profile JSON.
        metadata (CanonicalizedMetadata): Canonicalized profile metadata arrays.

    Returns:
        CanonicalizedCustomerProfile: Validated profile-shaped canonicalized
        customer profile output.

    Raises:
        pydantic.ValidationError: If the profile output is malformed.
    """

    profile_input = customer_profile_to_canonicalization_input(profile)
    return CanonicalizedCustomerProfile.model_validate(
        {
            "client_name": _optional_profile_string(profile.get("client_name")),
            "ticker": _optional_profile_string(profile.get("ticker")),
            "sector": _first_canonical(
                items=metadata.sectors,
                source_fields=profile_input.metadata_fields["sectors"],
                profile_fields=PROFILE_SECTOR_FIELDS,
            ),
            **_project_profile_company_fields(
                metadata=metadata,
                source_fields=profile_input.company_fields,
            ),
            **_project_profile_metadata_fields(
                metadata=metadata,
                source_fields_by_field=profile_input.metadata_fields,
            ),
        }
    )


def canonicalize_customer_profile(
    profile: Mapping[str, object],
    catalog: CanonicalCatalog,
    model: CanonicalizationStructuredOutputModel,
    candidate_generator: CanonicalCandidateGenerator,
) -> CanonicalizedCustomerProfile:
    """Canonicalize one customer profile through the shared service.

    Args:
        profile (Mapping[str, object]): Decoded customer profile JSON object.
        catalog (CanonicalCatalog): Canonical catalog used for validation.
        model (CanonicalizationStructuredOutputModel): Structured-output-capable
            model used for canonical decisions.
        candidate_generator (CanonicalCandidateGenerator): Candidate generator
            shared across canonicalization calls.

    Returns:
        CanonicalizedCustomerProfile: Validated canonicalized customer profile.

    Raises:
        ValueError: If profile adaptation or model decisions are invalid.
        pydantic.ValidationError: If adapted payloads or canonicalized outputs
            fail schema validation.
    """

    profile_input = customer_profile_to_canonicalization_input(profile)
    metadata = canonicalize_payload(
        payload=profile_input.payload,
        catalog=catalog,
        model=model,
        candidate_generator=candidate_generator,
    )
    return canonicalized_metadata_to_customer_profile(
        profile=profile,
        metadata=metadata,
    )


def canonicalize_enriched_alerts(
    alerts: Sequence[EnrichedAlert],
    catalog: CanonicalCatalog,
    model: CanonicalizationStructuredOutputModel,
    candidate_generator: CanonicalCandidateGenerator,
) -> list[CanonicalizedAlert]:
    """Canonicalize enriched alerts with one decision request per alert.

    Args:
        alerts (Sequence[EnrichedAlert]): Enriched alerts to canonicalize.
        catalog (CanonicalCatalog): Canonical catalog used for validation.
        model (CanonicalizationStructuredOutputModel): Structured-output-capable
            model used for canonical decisions.
        candidate_generator (CanonicalCandidateGenerator): Candidate generator
            shared across alert canonicalization calls.

    Returns:
        list[CanonicalizedAlert]: Canonicalized alerts in source order.

    Raises:
        ValueError: If any model decision is invalid.
        pydantic.ValidationError: If model responses or outputs fail schema
            validation.
    """

    return [
        canonicalize_alert(
            alert=alert,
            catalog=catalog,
            model=model,
            candidate_generator=candidate_generator,
        )
        for alert in alerts
    ]


def run_canonicalization_processing(
    input_path: Path | str,
    client_profile_path: Path | str,
    alert_output_path: Path | str,
    profile_output_path: Path | str,
    catalog: CanonicalCatalog,
    model: CanonicalizationStructuredOutputModel,
    candidate_generator: CanonicalCandidateGenerator,
) -> CanonicalizationProcessingResult:
    """Read, canonicalize, validate, and write alert/profile outputs.

    Args:
        input_path (Path | str): Enriched alerts JSON array path.
        client_profile_path (Path | str): Customer profile JSON object path.
        alert_output_path (Path | str): Canonicalized alerts JSON array output
            path. Records are merged by alert ``id``.
        profile_output_path (Path | str): Canonicalized customer profile JSON
            object output path.
        catalog (CanonicalCatalog): Canonical catalog used for validation.
        model (CanonicalizationStructuredOutputModel): Structured-output-capable
            model used for canonical decisions.
        candidate_generator (CanonicalCandidateGenerator): Candidate generator
            shared across alert and profile canonicalization calls.

    Returns:
        CanonicalizationProcessingResult: Validated canonicalized outputs from
        the current run.

    Raises:
        OSError: If input files cannot be read or outputs cannot be written.
        json.JSONDecodeError: If an input or existing output file is malformed
            JSON.
        ValueError: If input roots, profile mappings, model decisions, or
            existing record stores are invalid.
        pydantic.ValidationError: If loaded records, model responses, or output
            schemas fail validation.
    """

    storage = StorageBackend()
    loader = AlertDataLoader(storage=storage)
    enriched_alerts = loader.load_enriched_alerts(input_path)
    profile = loader.load_client_profile_context(client_profile_path)

    canonicalized_alerts = canonicalize_enriched_alerts(
        alerts=enriched_alerts,
        catalog=catalog,
        model=model,
        candidate_generator=candidate_generator,
    )
    canonicalized_profile = canonicalize_customer_profile(
        profile=profile,
        catalog=catalog,
        model=model,
        candidate_generator=candidate_generator,
    )

    JsonRecordStore(path=alert_output_path, storage=storage).merge_records(
        canonicalized_alerts
    )
    storage.write_json(
        path=profile_output_path,
        data=canonicalized_profile.model_dump(mode="json", exclude_none=True),
    )

    return CanonicalizationProcessingResult(
        alerts=canonicalized_alerts,
        customer_profile=canonicalized_profile,
    )


def _metadata_dump(alert: EnrichedAlert) -> dict[str, object]:
    """Serialize canonical metadata fields from an enriched alert."""

    alert_data = alert.model_dump(mode="json")
    return {field: alert_data[field] for field in CANONICAL_FIELDS}


def _profile_source_id(profile: Mapping[str, object]) -> str:
    """Return a stable profile source ID for traceability."""

    ticker = profile.get("ticker")
    if isinstance(ticker, str) and ticker.strip():
        return ticker.strip()
    client_name = profile.get("client_name")
    if isinstance(client_name, str) and client_name.strip():
        return client_name.strip()
    return "customer_profile"


def _profile_company_items(
    profile: Mapping[str, object],
) -> tuple[list[dict[str, object]], tuple[str, ...]]:
    """Build company metadata items and source profile fields."""

    company_items: list[dict[str, object]] = []
    source_fields: list[str] = []
    profile_ticker = _optional_profile_string(profile.get("ticker"))
    for field in PROFILE_COMPANY_FIELDS:
        for value in _profile_values(profile, field):
            item = _profile_company_item(value=value, profile_field=field)
            if field == "client_name" and item["ticker"] is None:
                item["ticker"] = profile_ticker
            company_items.append(item)
            source_fields.append(field)
    return company_items, tuple(source_fields)


def _profile_metadata_items(
    profile: Mapping[str, object],
    profile_fields: Sequence[str],
) -> tuple[list[dict[str, object]], tuple[str, ...]]:
    """Build non-company metadata items and source profile fields."""

    items: list[dict[str, object]] = []
    source_fields: list[str] = []
    for field in profile_fields:
        for value in _profile_values(profile, field):
            items.append(_profile_metadata_item(value=value, profile_field=field))
            source_fields.append(field)
    return items, tuple(source_fields)


def _project_profile_company_fields(
    metadata: CanonicalizedMetadata,
    source_fields: Sequence[str],
) -> dict[str, list[str]]:
    """Project canonical company IDs into profile relationship fields."""

    output: dict[str, list[str]] = {}
    for profile_field in PROFILE_OUTPUT_COMPANY_FIELDS:
        output[profile_field] = _deduplicated_canonical_ids(
            item.canonical
            for item, source_field in zip(
                metadata.companies,
                source_fields,
                strict=True,
            )
            if source_field == profile_field
        )
    return output


def _project_profile_metadata_fields(
    metadata: CanonicalizedMetadata,
    source_fields_by_field: Mapping[str, Sequence[str]],
) -> dict[str, list[str]]:
    """Project canonical metadata IDs into profile-shaped metadata fields."""

    output: dict[str, list[str]] = {}
    for field in PROFILE_OUTPUT_METADATA_FIELDS:
        output[field] = _deduplicated_canonical_ids(
            item.canonical
            for item, source_field in zip(
                getattr(metadata, field),
                source_fields_by_field[field],
                strict=True,
            )
            if source_field == field
        )
    return output


def _first_canonical(
    items: Sequence[CanonicalMetadataItem],
    source_fields: Sequence[str],
    profile_fields: Sequence[str],
) -> str | None:
    """Return the first non-null canonical ID for selected profile fields."""

    for profile_field in profile_fields:
        for item, source_field in zip(items, source_fields, strict=True):
            if source_field != profile_field or item.canonical is None:
                continue
            return item.canonical
    return None


def _deduplicated_canonical_ids(canonical_values: Iterable[str | None]) -> list[str]:
    """Return non-null canonical IDs deduplicated in first-seen order."""

    seen: set[str] = set()
    result: list[str] = []
    for canonical in canonical_values:
        if canonical is None or canonical in seen:
            continue
        seen.add(canonical)
        result.append(canonical)
    return result


def _profile_values(profile: Mapping[str, object], field: str) -> list[object]:
    """Return normalized raw values for one profile field."""

    if field not in profile or profile[field] is None:
        return []

    value = profile[field]
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, Sequence):
        return list(value)
    raise ValueError(f"Profile field {field!r} must be a string, object, or array")


def _profile_company_item(value: object, profile_field: str) -> dict[str, object]:
    """Build one company metadata item from a profile value."""

    if isinstance(value, str):
        return {
            "name": _require_profile_name(value=value, profile_field=profile_field),
            "ticker": None,
            "rationale": f"Customer profile field {profile_field} value.",
        }
    if isinstance(value, Mapping):
        name = _require_profile_name(
            value=value.get("name"),
            profile_field=profile_field,
        )
        return {
            "name": name,
            "ticker": _optional_profile_string(value.get("ticker")),
            "rationale": _profile_rationale(value=value, profile_field=profile_field),
        }
    raise ValueError(
        f"Profile field {profile_field!r} values must be strings or objects"
    )


def _profile_metadata_item(value: object, profile_field: str) -> dict[str, object]:
    """Build one non-company metadata item from a profile value."""

    if isinstance(value, str):
        return {
            "name": _require_profile_name(value=value, profile_field=profile_field),
            "rationale": f"Customer profile field {profile_field} value.",
        }
    if isinstance(value, Mapping):
        name = _require_profile_name(
            value=value.get("name"),
            profile_field=profile_field,
        )
        return {
            "name": name,
            "rationale": _profile_rationale(value=value, profile_field=profile_field),
        }
    raise ValueError(
        f"Profile field {profile_field!r} values must be strings or objects"
    )


def _profile_rationale(value: Mapping[str, object], profile_field: str) -> str:
    """Return explicit or generated rationale for a profile object value."""

    rationale = value.get("rationale")
    if isinstance(rationale, str) and rationale.strip():
        return rationale
    return f"Customer profile field {profile_field} value."


def _require_profile_name(value: object, profile_field: str) -> str:
    """Return a non-empty string name from a profile value."""

    if isinstance(value, str) and value.strip():
        return value
    raise ValueError(f"Profile field {profile_field!r} contains a missing name")


def _optional_profile_string(value: object) -> str | None:
    """Return an optional non-empty string from a profile value."""

    if isinstance(value, str) and value.strip():
        return value
    return None


__all__ = [
    "CanonicalizationProcessingResult",
    "ProfileCanonicalizationInput",
    "canonicalize_customer_profile",
    "canonicalize_enriched_alerts",
    "canonicalized_metadata_to_alert",
    "canonicalized_metadata_to_customer_profile",
    "customer_profile_to_canonicalization_input",
    "customer_profile_to_payload",
    "enriched_alert_to_payload",
    "run_canonicalization_processing",
]

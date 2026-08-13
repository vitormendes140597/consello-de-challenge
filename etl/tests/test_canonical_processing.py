"""Tests for canonicalization processing adapters and IO orchestration."""

from __future__ import annotations

import json
from collections.abc import Mapping

from etl.canonicalization.candidates import CanonicalCandidateGenerator
from etl.canonicalization.processing import (
    canonicalized_metadata_to_alert,
    canonicalized_metadata_to_customer_profile,
    customer_profile_to_canonicalization_input,
    customer_profile_to_payload,
    enriched_alert_to_payload,
    run_canonicalization_processing,
)
from etl.canonicalization.schemas import (
    CanonicalCatalog,
    CanonicalizationDecision,
    CanonicalCompanyItem,
    CanonicalizedMetadata,
    CanonicalMetadataItem,
)
from etl.common.fields import CANONICAL_FIELDS
from etl.common.schemas import EnrichedAlert


def test_enriched_alert_to_payload_preserves_metadata_with_trace_fields() -> None:
    """Verify enriched alerts adapt to the common canonicalization payload."""

    alert = EnrichedAlert(
        id="a01",
        received_at="2026-08-11T09:00:00+00:00",
        subject="Solstice reports earnings",
        body="Solstice Robotics reported demand.",
        companies=[
            {
                "name": "Solstice Robotics",
                "ticker": "SLRB",
                "rationale": "The source names Solstice Robotics.",
            }
        ],
    )

    payload = enriched_alert_to_payload(alert)

    assert payload.source_type == "alert"
    assert payload.source_id == "a01"
    assert payload.companies[0].name == "Solstice Robotics"
    assert payload.companies[0].ticker == "SLRB"


def test_customer_profile_to_payload_maps_supported_profile_fields() -> None:
    """Verify profile-specific fields map into canonical metadata arrays."""

    payload = customer_profile_to_payload(
        {
            "client_name": "Solstice Robotics",
            "ticker": "SLRB",
            "focal_companies": ["Solstice"],
            "competitors": ["Kestrel Automation"],
            "suppliers": ["Ferrotech Alloys"],
            "customers": ["Northline Logistics"],
            "sector": "Industrial Automation & Robotics",
            "geo_markets": ["Germany"],
            "key_markets": ["warehouse automation"],
            "commodities": ["rare earth magnets"],
            "regulators": ["CFIUS"],
            "macro_sensitivities": ["interest rates"],
            "themes": ["AI-driven automation"],
        }
    )

    assert payload.source_type == "customer_profile"
    assert payload.source_id == "SLRB"
    assert [company.name for company in payload.companies] == [
        "Solstice Robotics",
        "Solstice",
        "Kestrel Automation",
        "Ferrotech Alloys",
        "Northline Logistics",
    ]
    assert payload.companies[0].ticker == "SLRB"
    assert payload.sectors[0].name == "Industrial Automation & Robotics"
    assert payload.geo_markets[0].name == "Germany"
    assert payload.key_markets[0].name == "warehouse automation"
    assert payload.commodities[0].name == "rare earth magnets"
    assert payload.regulators[0].name == "CFIUS"
    assert payload.macro_sensitivities[0].name == "interest rates"
    assert payload.themes[0].name == "AI-driven automation"


def test_customer_profile_to_canonicalization_input_tracks_source_fields() -> None:
    """Verify profile item provenance is stored outside rationale strings."""

    profile_input = customer_profile_to_canonicalization_input(
        {
            "client_name": "Solstice Robotics",
            "ticker": "SLRB",
            "focal_companies": ["Solstice"],
            "competitors": ["Kestrel Automation"],
            "suppliers": ["Ferrotech Alloys"],
            "customers": ["Northline Logistics"],
            "sector": "Industrial Automation & Robotics",
            "key_markets": ["warehouse automation"],
        }
    )

    assert profile_input.company_fields == (
        "client_name",
        "focal_companies",
        "competitors",
        "suppliers",
        "customers",
    )
    assert profile_input.metadata_fields["sectors"] == ("sector",)
    assert profile_input.metadata_fields["key_markets"] == ("key_markets",)


def test_customer_profile_to_payload_preserves_object_metadata_rationales() -> None:
    """Verify object-shaped profile metadata arrays keep names and rationales."""

    payload = customer_profile_to_payload(
        {
            "companies": [
                {
                    "name": "Delta Servo Corp",
                    "ticker": "DSC",
                    "rationale": "Existing profile company rationale.",
                }
            ],
            "sectors": [
                {
                    "name": "Industrial Robotics",
                    "rationale": "Existing profile sector rationale.",
                }
            ],
            "themes": [
                {
                    "name": "supply chain resilience",
                    "rationale": "Existing profile theme rationale.",
                }
            ],
        }
    )

    assert payload.companies[0].name == "Delta Servo Corp"
    assert payload.companies[0].ticker == "DSC"
    assert payload.companies[0].rationale == "Existing profile company rationale."
    assert payload.sectors[0].name == "Industrial Robotics"
    assert payload.sectors[0].rationale == "Existing profile sector rationale."
    assert payload.themes[0].name == "supply chain resilience"
    assert payload.themes[0].rationale == "Existing profile theme rationale."


def test_canonicalized_metadata_conversion_preserves_source_objects() -> None:
    """Verify conversion helpers produce validated alert and profile outputs."""

    alert = EnrichedAlert(
        id="a01",
        received_at="2026-08-11T09:00:00+00:00",
        subject="Solstice reports earnings",
        body="Solstice Robotics reported demand.",
    )
    metadata = CanonicalizedMetadata(
        companies=[
            CanonicalCompanyItem(
                name="Solstice Robotics",
                ticker="SLRB",
                canonical="solstice_robotics",
                rationale="Profile client company.",
            )
        ],
        sectors=[
            CanonicalMetadataItem(
                name="Industrial Automation & Robotics",
                canonical="industrial_automation",
                rationale="Profile sector.",
            )
        ]
    )

    canonicalized_alert = canonicalized_metadata_to_alert(
        alert=alert,
        metadata=metadata,
    )
    canonicalized_profile = canonicalized_metadata_to_customer_profile(
        profile={
            "client_name": "Solstice Robotics",
            "ticker": "SLRB",
            "sector": "Industrial Automation & Robotics",
        },
        metadata=metadata,
    )

    assert canonicalized_alert.id == "a01"
    assert canonicalized_alert.subject == "Solstice reports earnings"
    assert canonicalized_alert.sectors[0].canonical == "industrial_automation"
    assert canonicalized_profile.client_name == "Solstice Robotics"
    assert canonicalized_profile.ticker == "SLRB"
    assert canonicalized_profile.sector == "industrial_automation"


def test_canonicalized_profile_projection_preserves_relationship_fields() -> None:
    """Verify company fields project back to their profile relationships."""

    profile = {
        "client_name": "Solstice Robotics",
        "ticker": "SLRB",
        "focal_companies": ["Solstice Robotics", "Solstice"],
        "competitors": ["Kestrel Automation"],
        "suppliers": ["Ferrotech Alloys"],
        "customers": ["Northline Logistics"],
        "sector": "Industrial Automation & Robotics",
        "geo_markets": ["Germany"],
        "key_markets": ["industrial automation", "warehouse automation"],
        "regulators": ["EU AI Act", "CFIUS"],
    }
    metadata = CanonicalizedMetadata(
        companies=[
            CanonicalCompanyItem(
                name="Solstice Robotics",
                ticker="SLRB",
                canonical="solstice_robotics",
                rationale="Customer profile field client_name value.",
            ),
            CanonicalCompanyItem(
                name="Solstice Robotics",
                ticker=None,
                canonical="solstice_robotics",
                rationale="Customer profile field focal_companies value.",
            ),
            CanonicalCompanyItem(
                name="Solstice",
                ticker=None,
                canonical="solstice_robotics",
                rationale="Custom rationale should not be parsed.",
            ),
            CanonicalCompanyItem(
                name="Kestrel Automation",
                ticker=None,
                canonical="kestrel_automation",
                rationale="Customer profile field competitors value.",
            ),
            CanonicalCompanyItem(
                name="Ferrotech Alloys",
                ticker=None,
                canonical="ferrotech_alloys",
                rationale="Customer profile field suppliers value.",
            ),
            CanonicalCompanyItem(
                name="Northline Logistics",
                ticker=None,
                canonical="northline_logistics",
                rationale="Customer profile field customers value.",
            ),
        ],
        sectors=[
            CanonicalMetadataItem(
                name="Industrial Automation & Robotics",
                canonical="industrial_automation",
                rationale="Customer profile field sector value.",
            )
        ],
        geo_markets=[
            CanonicalMetadataItem(
                name="Germany",
                canonical="germany",
                rationale="Customer profile field geo_markets value.",
            )
        ],
        key_markets=[
            CanonicalMetadataItem(
                name="industrial automation",
                canonical=None,
                rationale="Customer profile field key_markets value.",
            ),
            CanonicalMetadataItem(
                name="warehouse automation",
                canonical="warehouse_automation",
                rationale="Customer profile field key_markets value.",
            ),
        ],
        regulators=[
            CanonicalMetadataItem(
                name="EU AI Act",
                canonical=None,
                rationale="Customer profile field regulators value.",
            ),
            CanonicalMetadataItem(
                name="CFIUS",
                canonical="cfius",
                rationale="Customer profile field regulators value.",
            ),
        ],
    )

    canonicalized_profile = canonicalized_metadata_to_customer_profile(
        profile=profile,
        metadata=metadata,
    )

    assert canonicalized_profile.client_name == "Solstice Robotics"
    assert canonicalized_profile.ticker == "SLRB"
    assert canonicalized_profile.sector == "industrial_automation"
    assert canonicalized_profile.focal_companies == ["solstice_robotics"]
    assert canonicalized_profile.competitors == ["kestrel_automation"]
    assert canonicalized_profile.suppliers == ["ferrotech_alloys"]
    assert canonicalized_profile.customers == ["northline_logistics"]
    assert canonicalized_profile.geo_markets == ["germany"]
    assert canonicalized_profile.key_markets == ["warehouse_automation"]
    assert canonicalized_profile.regulators == ["cfius"]


def test_run_canonicalization_processing_writes_separate_outputs(tmp_path) -> None:
    """Verify processing reads enriched/profile inputs and writes outputs."""

    enriched_path = tmp_path / "processed" / "enriched_alerts.json"
    alert_output_path = tmp_path / "processed" / "canonicalized_alerts.json"
    profile_path = tmp_path / "raw" / "client_profile.json"
    profile_output_path = tmp_path / "processed" / "canonicalized_profile.json"
    enriched_path.parent.mkdir(parents=True)
    profile_path.parent.mkdir(parents=True)
    enriched_records = [
        {
            "id": "a01",
            "received_at": "2026-08-11T09:00:00+00:00",
            "subject": "Solstice reports earnings",
            "body": "Solstice Robotics reported demand.",
            "companies": [
                {
                    "name": "Solstice Robotics",
                    "ticker": "SLRB",
                    "rationale": "The source names Solstice Robotics.",
                }
            ],
        }
    ]
    enriched_path.write_text(json.dumps(enriched_records), encoding="utf-8")
    alert_output_path.write_text(
        json.dumps(
            [
                {
                    "id": "a99",
                    "received_at": "2026-08-01T09:00:00+00:00",
                    "subject": "Preserved alert",
                    "body": "Preserved body.",
                    **_empty_canonical_fields(),
                },
                {
                    "id": "a01",
                    "received_at": "2026-08-01T09:00:00+00:00",
                    "subject": "Stale alert",
                    "body": "Stale body.",
                    **_empty_canonical_fields(),
                },
            ]
        ),
        encoding="utf-8",
    )
    profile_path.write_text(
        json.dumps(
            {
                "client_name": "Solstice Robotics",
                "ticker": "SLRB",
                "key_markets": ["warehouse automation"],
            }
        ),
        encoding="utf-8",
    )
    structured_model = FakeStructuredCanonicalizationModel(
        [
            {
                "companies": [{"canonical": "solstice_robotics"}],
            },
            {
                "companies": [{"canonical": "solstice_robotics"}],
                "key_markets": [{"canonical": "warehouse_automation"}],
            },
        ]
    )
    model = FakeCanonicalizationModel(structured_model)
    catalog = _catalog()

    result = run_canonicalization_processing(
        input_path=enriched_path,
        client_profile_path=profile_path,
        alert_output_path=alert_output_path,
        profile_output_path=profile_output_path,
        catalog=catalog,
        model=model,
        candidate_generator=CanonicalCandidateGenerator(catalog),
    )

    written_alerts = json.loads(alert_output_path.read_text(encoding="utf-8"))
    written_profile = json.loads(profile_output_path.read_text(encoding="utf-8"))
    assert result.alerts[0].companies[0].canonical == "solstice_robotics"
    assert result.customer_profile.key_markets == ["warehouse_automation"]
    assert json.loads(enriched_path.read_text(encoding="utf-8")) == enriched_records
    assert [record["id"] for record in written_alerts] == ["a99", "a01"]
    assert written_alerts[1]["subject"] == "Solstice reports earnings"
    assert written_alerts[1]["companies"][0]["canonical"] == "solstice_robotics"
    assert written_profile["client_name"] == "Solstice Robotics"
    assert written_profile["ticker"] == "SLRB"
    assert written_profile["key_markets"] == ["warehouse_automation"]
    assert structured_model.invoke_count == 2
    assert model.schema_bindings == [
        CanonicalizationDecision,
        CanonicalizationDecision,
    ]


class FakeStructuredCanonicalizationModel:
    """Fake structured runnable that returns queued canonicalization decisions."""

    def __init__(self, responses: list[Mapping[str, object]]) -> None:
        """Store fake canonicalization responses.

        Args:
            responses (list[Mapping[str, object]]): Responses returned by
                sequential invocations.
        """

        self.responses = responses
        self.prompts: list[str] = []
        self.invoke_count = 0

    def invoke(self, prompt: str) -> Mapping[str, object]:
        """Record the prompt and return the next response.

        Args:
            prompt (str): Canonicalization prompt.

        Returns:
            Mapping[str, object]: Next queued decision response.
        """

        self.prompts.append(prompt)
        self.invoke_count += 1
        return self.responses.pop(0)


class FakeCanonicalizationModel:
    """Fake chat model that records structured-output schema bindings."""

    def __init__(self, structured_model: FakeStructuredCanonicalizationModel) -> None:
        """Store the structured model returned by schema binding.

        Args:
            structured_model (FakeStructuredCanonicalizationModel): Runnable
                returned for every structured-output binding.
        """

        self.structured_model = structured_model
        self.schema_bindings: list[type[CanonicalizationDecision]] = []

    def with_structured_output(
        self,
        schema: type[CanonicalizationDecision],
    ) -> FakeStructuredCanonicalizationModel:
        """Record the schema and return the fake structured runnable.

        Args:
            schema (type[CanonicalizationDecision]): Requested output schema.

        Returns:
            FakeStructuredCanonicalizationModel: Runnable used by processing.
        """

        self.schema_bindings.append(schema)
        return self.structured_model


def _catalog() -> CanonicalCatalog:
    """Create a minimal valid catalog for processing tests.

    Returns:
        CanonicalCatalog: Test catalog with deterministic label matches.
    """

    values_by_field = {
        "companies": {
            "solstice_robotics": {
                "label": "Solstice Robotics",
                "aliases": ["SLRB", "Solstice"],
                "description": "Tracked robotics company.",
            }
        },
        "key_markets": {
            "warehouse_automation": {
                "label": "Warehouse Automation",
                "aliases": ["warehouse automation"],
                "description": "Warehouse automation market.",
            }
        },
        "sectors": {
            "industrial_automation": {
                "label": "Industrial Automation",
                "aliases": ["Industrial Automation & Robotics"],
                "description": "Industrial automation sector.",
            }
        },
    }

    return CanonicalCatalog.model_validate(
        {
            "version": 1,
            "fields": {
                field: {
                    "description": f"{field} field",
                    "values": values_by_field.get(
                        field,
                        {
                            f"{field}_value": {
                                "label": f"{field} value",
                                "description": f"{field} description",
                            }
                        },
                    ),
                }
                for field in CANONICAL_FIELDS
            },
        }
    )


def _empty_canonical_fields() -> dict[str, object]:
    """Return empty canonicalized metadata arrays for all supported fields.

    Returns:
        dict[str, object]: Empty canonicalized metadata fields.
    """

    return {field: [] for field in CANONICAL_FIELDS}

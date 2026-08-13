"""Tests for canonicalization decision orchestration."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from etl.canonicalization.candidates import CanonicalCandidateGenerator
from etl.canonicalization.schemas import (
    CanonicalCatalog,
    CanonicalizationDecision,
    CanonicalizationPayload,
)
from etl.canonicalization.service import canonicalize_alert, canonicalize_payload
from etl.common.fields import CANONICAL_FIELDS
from etl.common.schemas import (
    EnrichedAlert,
)


def test_canonicalize_alert_uses_one_structured_decision_and_preserves_items() -> None:
    """Verify alert canonicalization preserves source item data."""

    catalog = _catalog()
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
    structured_model = FakeStructuredCanonicalizationModel(
        {
            "companies": [
                {
                    "canonical": "companies_value",
                }
            ]
        }
    )
    model = FakeCanonicalizationModel(structured_model)

    canonicalized = canonicalize_alert(
        alert=alert,
        catalog=catalog,
        model=model,
        candidate_generator=CanonicalCandidateGenerator(catalog),
    )

    assert model.schema is CanonicalizationDecision
    assert structured_model.invoke_count == 1
    assert "<projected_candidates>" in structured_model.prompt
    assert canonicalized.companies[0].name == "Solstice Robotics"
    assert canonicalized.companies[0].ticker == "SLRB"
    assert canonicalized.companies[0].rationale == (
        "The source names Solstice Robotics."
    )
    assert canonicalized.companies[0].canonical == "companies_value"


def test_canonicalize_payload_handles_profile_payload() -> None:
    """Verify common profile payloads can be canonicalized in one decision."""

    catalog = _catalog()
    payload = CanonicalizationPayload(
        source_type="customer_profile",
        source_id="profile",
        sectors=[
            {
                "name": "sectors value",
                "rationale": "Profile sector.",
            }
        ],
    )
    structured_model = FakeStructuredCanonicalizationModel(
        {
            "sectors": [
                {
                    "canonical": "sectors_value",
                }
            ]
        }
    )
    model = FakeCanonicalizationModel(structured_model)

    canonicalized = canonicalize_payload(
        payload=payload,
        catalog=catalog,
        model=model,
        candidate_generator=CanonicalCandidateGenerator(catalog),
    )

    assert structured_model.invoke_count == 1
    assert canonicalized.sectors[0].name == "sectors value"
    assert canonicalized.sectors[0].canonical == "sectors_value"


def test_canonicalization_rejects_changed_item_counts() -> None:
    """Verify model decisions cannot add or remove item positions."""

    catalog = _catalog()
    alert = EnrichedAlert(
        id="a01",
        received_at="2026-08-11T09:00:00+00:00",
        subject="Solstice reports earnings",
        body="Solstice Robotics reported demand.",
        themes=[
            {
                "name": "themes value",
                "rationale": "The source cites a theme.",
            }
        ],
    )
    model = FakeCanonicalizationModel(FakeStructuredCanonicalizationModel({}))

    with pytest.raises(ValueError, match="changed item count"):
        canonicalize_alert(
            alert=alert,
            catalog=catalog,
            model=model,
            candidate_generator=CanonicalCandidateGenerator(catalog),
        )


def test_canonicalization_rejects_decision_outside_projected_candidates() -> None:
    """Verify decisions must be present in the item candidate set."""

    catalog = _catalog()
    alert = EnrichedAlert(
        id="a01",
        received_at="2026-08-11T09:00:00+00:00",
        subject="Solstice reports earnings",
        body="Solstice Robotics reported demand.",
        themes=[
            {
                "name": "themes value",
                "rationale": "The source cites a theme.",
            }
        ],
    )
    model = FakeCanonicalizationModel(
        FakeStructuredCanonicalizationModel(
            {
                "themes": [
                    {
                        "canonical": "unknown_theme",
                    }
                ]
            }
        )
    )

    with pytest.raises(ValueError, match="outside the projected candidates"):
        canonicalize_alert(
            alert=alert,
            catalog=catalog,
            model=model,
            candidate_generator=CanonicalCandidateGenerator(catalog),
        )


def test_regulator_canonicalization_accepts_entities_and_explicit_law_mapping() -> None:
    """Verify regulator names, acronyms, and explicit law mappings can canonicalize."""

    catalog = _catalog(
        overrides={
            "regulators": {
                "cfius": {
                    "label": "Committee on Foreign Investment in the United States",
                    "aliases": ["CFIUS"],
                    "law_or_regime_aliases": ["foreign investment review"],
                    "description": "US investment review committee.",
                }
            }
        }
    )
    alert = EnrichedAlert(
        id="a01",
        received_at="2026-08-11T09:00:00+00:00",
        subject="CFIUS opens review",
        body="The Committee on Foreign Investment opened a review.",
        regulators=[
            {
                "name": "CFIUS",
                "rationale": "Acronym appears in source.",
            },
            {
                "name": "Committee on Foreign Investment in the United States",
                "rationale": "Full regulator name appears in source.",
            },
            {
                "name": "foreign investment review",
                "rationale": "Review process appears in source.",
            },
        ],
    )
    model = FakeCanonicalizationModel(
        FakeStructuredCanonicalizationModel(
            {
                "regulators": [
                    {"canonical": "cfius"},
                    {"canonical": "cfius"},
                    {"canonical": "cfius"},
                ]
            }
        )
    )

    canonicalized = canonicalize_alert(
        alert=alert,
        catalog=catalog,
        model=model,
        candidate_generator=CanonicalCandidateGenerator(catalog),
    )

    assert [item.canonical for item in canonicalized.regulators] == [
        "cfius",
        "cfius",
        "cfius",
    ]


def test_regulator_unmapped_law_can_remain_null() -> None:
    """Verify unmapped regulator laws or regimes can canonicalize to null."""

    catalog = _catalog(
        overrides={
            "regulators": {
                "european_commission": {
                    "label": "European Commission",
                    "aliases": [],
                    "law_or_regime_aliases": [],
                    "description": "EU executive body.",
                }
            }
        }
    )
    alert = EnrichedAlert(
        id="a01",
        received_at="2026-08-11T09:00:00+00:00",
        subject="EU AI Act guidance",
        body="EU AI Act enforcement guidance was released.",
        regulators=[
            {
                "name": "EU AI Act",
                "rationale": "Law appears in source.",
            }
        ],
    )
    model = FakeCanonicalizationModel(
        FakeStructuredCanonicalizationModel({"regulators": [{"canonical": None}]})
    )

    canonicalized = canonicalize_alert(
        alert=alert,
        catalog=catalog,
        model=model,
        candidate_generator=CanonicalCandidateGenerator(catalog),
    )

    assert canonicalized.regulators[0].canonical is None


def test_regulator_embedding_similar_unmapped_law_is_rejected() -> None:
    """Verify embedding-only law mappings cannot become regulator outputs."""

    catalog = _catalog(
        overrides={
            "regulators": {
                "european_commission": {
                    "label": "European Commission",
                    "aliases": [],
                    "law_or_regime_aliases": [],
                    "description": "EU executive body.",
                }
            }
        }
    )
    alert = EnrichedAlert(
        id="a01",
        received_at="2026-08-11T09:00:00+00:00",
        subject="EU AI Act guidance",
        body="EU AI Act enforcement guidance was released.",
        regulators=[
            {
                "name": "EU AI Act",
                "rationale": "Law appears in source.",
            }
        ],
    )
    model = FakeCanonicalizationModel(
        FakeStructuredCanonicalizationModel(
            {"regulators": [{"canonical": "european_commission"}]}
        )
    )

    with pytest.raises(ValueError, match="law_or_regime_alias"):
        canonicalize_alert(
            alert=alert,
            catalog=catalog,
            model=model,
            candidate_generator=CanonicalCandidateGenerator(
                catalog=catalog,
                embedding_client=FakeEmbeddingClient(vector=[1.0, 0.0]),
            ),
        )


class FakeStructuredCanonicalizationModel:
    """Fake structured runnable that records canonicalization prompts."""

    def __init__(
        self,
        response: CanonicalizationDecision | Mapping[str, object],
    ) -> None:
        """Store the fake canonicalization response."""

        self.response = response
        self.prompt = ""
        self.invoke_count = 0

    def invoke(
        self,
        prompt: str,
    ) -> CanonicalizationDecision | Mapping[str, object]:
        """Record the prompt and return the fake response."""

        self.prompt = prompt
        self.invoke_count += 1
        return self.response


class FakeCanonicalizationModel:
    """Fake chat model that records canonicalization schema binding."""

    def __init__(
        self,
        structured_model: FakeStructuredCanonicalizationModel,
    ) -> None:
        """Store the fake structured model returned by schema binding."""

        self.structured_model = structured_model
        self.schema: type[CanonicalizationDecision] | None = None

    def with_structured_output(
        self,
        schema: type[CanonicalizationDecision],
    ) -> FakeStructuredCanonicalizationModel:
        """Record the schema and return the fake structured model."""

        self.schema = schema
        return self.structured_model


class FakeEmbeddingClient:
    """Fake embedding client used to avoid network calls."""

    def __init__(self, vector: list[float]) -> None:
        """Store the vector returned for every input text."""

        self.vector = vector

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return the configured vector for each input text."""

        return [self.vector for _ in texts]


def _catalog(
    overrides: dict[str, dict[str, dict[str, object]]] | None = None,
) -> CanonicalCatalog:
    """Create a minimal valid canonical catalog for orchestration tests.

    Args:
        overrides (dict[str, dict[str, dict[str, object]]] | None): Optional
            field-specific catalog values.

    Returns:
        CanonicalCatalog: Catalog with one label-matching value per field.
    """

    fields = {
        field: {
            "description": f"{field} field",
            "values": {
                f"{field}_value": {
                    "label": f"{field} value",
                    "aliases": ["Solstice Robotics"] if field == "companies" else [],
                    "description": f"{field} description",
                }
            },
        }
        for field in CANONICAL_FIELDS
    }
    for field, values in (overrides or {}).items():
        fields[field] = {
            "description": f"{field} field",
            "values": values,
        }

    return CanonicalCatalog.model_validate(
        {
            "version": 1,
            "fields": fields,
        }
    )

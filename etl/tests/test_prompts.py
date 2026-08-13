"""Tests for alert extraction prompt construction."""

from etl.canonicalization.prompts import (
    CANONICALIZATION_FIELD_GUIDANCE,
    build_canonicalization_prompt,
)
from etl.canonicalization.schemas import CanonicalCandidateProjection
from etl.common.fields import AI_EXTRACTED_FIELDS
from etl.extraction.prompts import (
    FIELD_PROMPT_SECTIONS,
    build_synthesis_prompt,
    format_context_hints,
)


def test_every_extracted_field_has_prompt_section() -> None:
    """Verify every AI-extracted field has reusable prompt guidance."""

    assert set(FIELD_PROMPT_SECTIONS) == set(AI_EXTRACTED_FIELDS)

    for field in AI_EXTRACTED_FIELDS:
        prompt_section = FIELD_PROMPT_SECTIONS[field]

        assert f"## {field}" in prompt_section
        assert "Purpose:" in prompt_section
        assert "Include:" in prompt_section
        assert "Exclude:" in prompt_section
        assert "Evidence standard:" in prompt_section


def test_synthesis_prompt_wraps_dynamic_sections_with_xml_tags() -> None:
    """Verify prompt dynamic content is delimited with XML-style tags."""

    prompt = build_synthesis_prompt(
        subject="Solstice expands in Mexico & Germany",
        body="Solstice Robotics opened a plant for warehouse automation.",
        context_hints={"geo_markets": ["Germany", "Mexico"]},
    )

    assert "<news>" in prompt
    assert "<subject>" in prompt
    assert "Solstice expands in Mexico &amp; Germany" in prompt
    assert "<body>" in prompt
    assert "<context_hints>" in prompt
    assert "<global_rules>" in prompt
    assert "<prompt_sections>" in prompt
    assert 'prompt_section name="companies"' in prompt
    assert "context only; not closed allowlists" in prompt


def test_synthesis_prompt_does_not_embed_output_schema_instructions() -> None:
    """Verify output-shape enforcement stays out of prompt text."""

    prompt = build_synthesis_prompt(
        subject="Solstice reports earnings",
        body="Solstice Robotics reported stronger warehouse automation demand.",
    )

    assert "Structured output instructions" not in prompt
    assert "structured output schema" not in prompt
    assert "Copy id" not in prompt


def test_format_context_hints_handles_missing_context() -> None:
    """Verify missing context remains explicit and simple."""

    assert format_context_hints() == "none provided"


def test_canonicalization_prompt_uses_projected_candidates_not_full_catalog() -> None:
    """Verify canonicalization prompt is built from source and candidates."""

    projection = CanonicalCandidateProjection(
        catalog_version=1,
        catalog_hash="catalog-hash",
        items=[
            {
                "field": "regulators",
                "item_index": 0,
                "name": "CFIUS",
                "normalized_name": "cfius",
                "candidates": [
                    {
                        "canonical_id": "cfius",
                        "label": "CFIUS",
                        "match_source": "label",
                        "description": "US investment review committee.",
                    }
                ],
            }
        ],
    )

    prompt = build_canonicalization_prompt(
        source_payload={
            "source_type": "customer_profile",
            "regulators": [{"name": "CFIUS", "rationale": "Profile value."}],
        },
        candidate_projection=projection,
    )

    assert "<source_payload>" in prompt
    assert "<projected_candidates>" in prompt
    assert "<global_rules>" in prompt
    assert "cfius" in prompt
    assert "Profile value." in prompt
    assert "Use only candidate IDs provided" in prompt
    assert "Prioritize precision over forced coverage" in prompt
    assert "regulator entity IDs" in prompt
    assert "law_or_regime_aliases" in prompt
    assert "unrelated_catalog_entry" not in prompt
    assert set(CANONICALIZATION_FIELD_GUIDANCE) == set(AI_EXTRACTED_FIELDS)

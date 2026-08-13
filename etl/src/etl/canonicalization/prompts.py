"""Prompt definitions for ETL metadata canonicalization."""

from __future__ import annotations

import json
from collections.abc import Mapping
from html import escape

from pydantic import BaseModel

from etl.common.fields import CANONICAL_FIELDS

CANONICALIZATION_PERSONA = (
    "You are a careful canonical data standardization analyst. Choose canonical "
    "IDs only from the projected candidates for each extracted item. Preserve "
    "semantic distinctions and prefer null over weak or unsupported matches."
)

GLOBAL_CANONICALIZATION_RULES = (
    "Use only candidate IDs provided for the specific source item.",
    "Return null when no projected candidate is sufficiently equivalent.",
    "Prioritize precision over forced coverage.",
    "Match by meaning, not just exact wording.",
    "Do not add, remove, reorder, rename, or rewrite source items.",
    "The output arrays must align exactly with source item order for each field.",
    "The ETL will preserve original names, rationales, and tickers outside the model.",
)

REGULATOR_CANONICALIZATION_GUIDANCE = (
    "Regulator canonical outputs must be regulator entity IDs. A law, regulation, "
    "regime, review process, or enforcement framework may map to a regulator "
    "entity only when it appears in a projected candidate generated from an "
    "explicit catalog law_or_regime_aliases relationship. Return null for "
    "regulator-related laws or regimes that are only semantically similar to a "
    "regulator but lack an explicit projected candidate."
)

CANONICALIZATION_FIELD_GUIDANCE = {
    "companies": (
        "Map named operating businesses to company canonical IDs. Tickers and "
        "strong aliases can support a match, but do not map markets, sectors, "
        "regulators, geographies, or commodities as companies."
    ),
    "sectors": (
        "Map broad industry or business vertical wording to sector canonical "
        "IDs. Preserve the difference between broad sectors and narrower product "
        "or customer markets."
    ),
    "geo_markets": (
        "Map countries, regions, or trade areas to geographic market canonical "
        "IDs. Do not map company names, product markets, or vague non-geographic "
        "phrases."
    ),
    "key_markets": (
        "Map product, application, customer, end-market, or demand-pool wording "
        "to key-market canonical IDs. Prefer null when the item is only a broad "
        "sector or theme."
    ),
    "commodities": (
        "Map raw materials, traded goods, physical inputs, and supply components "
        "to commodity canonical IDs. Do not map abstract supply themes or broad "
        "industries."
    ),
    "regulators": REGULATOR_CANONICALIZATION_GUIDANCE,
    "macro_sensitivities": (
        "Map broad economic or geopolitical drivers to macro-sensitivity "
        "canonical IDs. Keep these distinct from literal regulators, geographies, "
        "and strategic themes."
    ),
    "themes": (
        "Map strategic or investment themes to theme canonical IDs. Prefer null "
        "for one-off facts, literal entities, or narrow markets that do not match "
        "a projected theme candidate."
    ),
}


def build_canonicalization_prompt(
    source_payload: Mapping[str, object] | BaseModel,
    candidate_projection: Mapping[str, object] | BaseModel,
) -> str:
    """Build the model-facing prompt for one canonicalization decision.

    Args:
        source_payload (Mapping[str, object] | BaseModel): Complete structured
            source object being canonicalized.
        candidate_projection (Mapping[str, object] | BaseModel): Projected
            candidate payload for the source object. This must contain only
            item-specific candidates, not the full catalog.

    Returns:
        str: Complete prompt sent to the canonicalization model.
    """

    field_guidance = "\n\n".join(
        _xml_element(
            tag="field_guidance",
            content=CANONICALIZATION_FIELD_GUIDANCE[field],
            attributes={"name": field},
        )
        for field in CANONICAL_FIELDS
    )
    global_rules = "\n".join(f"- {rule}" for rule in GLOBAL_CANONICALIZATION_RULES)

    return "\n\n".join(
        (
            CANONICALIZATION_PERSONA,
            _xml_element(
                tag="source_payload",
                content=_format_json_payload(source_payload),
            ),
            _xml_element(
                tag="projected_candidates",
                content=_format_json_payload(candidate_projection),
            ),
            _xml_element(tag="global_rules", content=global_rules),
            "<canonicalization_field_guidance>",
            field_guidance,
            "</canonicalization_field_guidance>",
            _xml_element(
                tag="regulator_specific_guidance",
                content=REGULATOR_CANONICALIZATION_GUIDANCE,
            ),
        )
    )


def _format_json_payload(value: Mapping[str, object] | BaseModel) -> str:
    """Serialize a prompt payload as stable JSON.

    Args:
        value (Mapping[str, object] | BaseModel): Mapping or Pydantic model to
            serialize.

    Returns:
        str: Indented JSON representation suitable for prompt inclusion.
    """

    if isinstance(value, BaseModel):
        payload = value.model_dump(mode="json")
    else:
        payload = dict(value)
    return json.dumps(payload, indent=2, sort_keys=True)


def _xml_element(
    tag: str,
    content: str,
    attributes: Mapping[str, str] | None = None,
) -> str:
    """Format escaped prompt content inside one XML-style element.

    Args:
        tag (str): Element tag name.
        content (str): Text content to escape and wrap.
        attributes (Mapping[str, str] | None): Optional element attributes.

    Returns:
        str: XML-style element string with escaped content and attributes.
    """

    attribute_text = ""
    if attributes:
        attribute_text = "".join(
            f' {name}="{escape(value, quote=True)}"'
            for name, value in attributes.items()
        )

    return "\n".join(
        (
            f"<{tag}{attribute_text}>",
            escape(content, quote=False),
            f"</{tag}>",
        )
    )


__all__ = [
    "CANONICALIZATION_FIELD_GUIDANCE",
    "CANONICALIZATION_PERSONA",
    "GLOBAL_CANONICALIZATION_RULES",
    "REGULATOR_CANONICALIZATION_GUIDANCE",
    "build_canonicalization_prompt",
]

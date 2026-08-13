"""Prompt definitions for alert metadata extraction."""

from __future__ import annotations

import json
from collections.abc import Mapping
from html import escape

from etl.common.fields import AI_EXTRACTED_FIELDS, OUTPUT_FIELDS, SOURCE_FIELDS

OUTPUT_FIELD_SEMANTICS = {
    "id": (
        "Source alert identifier. Copy unchanged from input; never generate with AI."
    ),
    "received_at": (
        "Source alert receipt timestamp. Copy unchanged from input; never generate "
        "with AI."
    ),
    "subject": (
        "Source alert subject or headline. Copy unchanged from input; never generate "
        "with AI."
    ),
    "body": (
        "Source alert body text. Copy unchanged from input; never generate with AI."
    ),
    "companies": (
        "Named business entities relevant to the alert, including focal companies, "
        "competitors, suppliers, customers, partners, acquirers, acquisition "
        "targets, or other operating businesses. Exclude countries, regulators, "
        "markets, sectors, commodities, themes, and macro concepts."
    ),
    "sectors": (
        "Broad industries or business verticals affected by the alert. Keep these "
        "broader than a single company and distinct from customer or end markets "
        "when possible."
    ),
    "geo_markets": (
        "Countries or regions materially connected to operations, demand, supply "
        "chains, regulation, investment, or manufacturing in the alert. Exclude "
        "company names and generic phrases with no geographic meaning."
    ),
    "key_markets": (
        "Product markets, end markets, customer markets, or demand pools affected "
        "by the alert. These should be more specific than sectors."
    ),
    "commodities": (
        "Raw materials, traded goods, physical inputs, or components whose "
        "availability, pricing, or supply affects the alert. Exclude broad sectors "
        "and abstract themes."
    ),
    "regulators": (
        "Regulatory bodies, laws, agencies, enforcement regimes, or formal review "
        "processes mentioned or clearly implicated by the alert. Exclude general "
        "government references unless tied to regulatory action."
    ),
    "macro_sensitivities": (
        "Broad economic or geopolitical drivers that can affect valuation, demand, "
        "margins, financing, or supply chains."
    ),
    "themes": (
        "Strategic or investment themes that summarize why the alert matters "
        "across companies or markets. Prefer thematic summaries over literal "
        "entities."
    ),
}

EXTRACTION_PERSONA = (
    "You are a careful financial news metadata extraction analyst. Read only the "
    "provided alert text and contextual hints. Extract recall-oriented first-pass "
    "metadata for downstream canonicalization, keeping each concept in its proper "
    "field and grounding every rationale in the alert evidence."
)


def _field_prompt(
    field: str,
    purpose: str,
    include: str,
    exclude: str,
    evidence: str,
    normalization: str,
    rationale: str,
    edge_cases: str,
) -> str:
    """Build a reusable prompt section for one extracted metadata field.

    Args:
        field (str): Output field name the section describes.
        purpose (str): Why the field exists.
        include (str): Values the model should include.
        exclude (str): Values the model should exclude.
        evidence (str): Evidence threshold for extraction.
        normalization (str): Output normalization rule.
        rationale (str): Rationale-writing instruction.
        edge_cases (str): Field-specific edge-case guidance.

    Returns:
        str: Formatted prompt section for the field.
    """

    return "\n".join(
        (
            f"## {field}",
            f"Purpose: {purpose}",
            f"Include: {include}",
            f"Exclude: {exclude}",
            f"Evidence standard: {evidence}",
            f"Normalization: {normalization}",
            f"Rationale: {rationale}",
            f"Edge cases: {edge_cases}",
        )
    )


companies_prompt = _field_prompt(
    field="companies",
    purpose="Extract named operating businesses that are relevant to the alert.",
    include=(
        "Focal companies, competitors, suppliers, customers, partners, acquirers, "
        "acquisition targets, and other named business entities."
    ),
    exclude=(
        "Countries, regions, regulators, laws, markets, sectors, commodities, "
        "macro drivers, investment themes, people, and generic organization types."
    ),
    evidence=(
        "Include a company only when the subject or body names it or clearly refers "
        "to a specific operating business."
    ),
    normalization=(
        "Return company names in lower case. Return tickers in lower case when "
        "explicitly present or highly confident; otherwise use null."
    ),
    rationale="Explain the alert evidence that makes the company relevant.",
    edge_cases=(
        "Do not put a country, customer market, regulator, or commodity in "
        "companies even when it affects a company."
    ),
)

sectors_prompt = _field_prompt(
    field="sectors",
    purpose="Extract broad industries or business verticals affected by the alert.",
    include=(
        "Industries such as industrial automation, logistics, automotive, "
        "semiconductors, manufacturing, or robotics when materially affected."
    ),
    exclude=(
        "Single company names, specific product markets, customer markets, "
        "countries, regulators, commodities, and broad investment themes."
    ),
    evidence=(
        "Include a sector when the alert states it directly or the body gives clear "
        "industry-level context."
    ),
    normalization="Return sector names in lower case.",
    rationale="Explain the text evidence connecting the alert to the sector.",
    edge_cases=(
        "Prefer key_markets for narrower demand pools such as warehouse automation "
        "or automotive manufacturing."
    ),
)

geo_markets_prompt = _field_prompt(
    field="geo_markets",
    purpose="Extract countries or regions materially connected to the alert.",
    include=(
        "Countries, regions, trade blocs, or named geographies tied to operations, "
        "demand, supply chains, regulation, investment, or manufacturing."
    ),
    exclude=(
        "Company names, facility names without geographic meaning, vague phrases "
        "like overseas, and markets that are not geographic."
    ),
    evidence=(
        "Include a geography only when the subject or body mentions it or clearly "
        "ties it to the event."
    ),
    normalization="Return geographic market names in lower case.",
    rationale="Explain why the geography matters to the alert.",
    edge_cases=(
        "A city can support a country or region when the country or region is "
        "material to the event."
    ),
)

key_markets_prompt = _field_prompt(
    field="key_markets",
    purpose="Extract specific product, end, customer, or demand markets.",
    include=(
        "Markets such as warehouse automation, automotive manufacturing, "
        "e-commerce fulfillment, control chips, or robotics components."
    ),
    exclude=(
        "Broad sectors, individual company names, countries, regulators, raw "
        "materials, and abstract themes."
    ),
    evidence=(
        "Include a key market when the alert ties products, customers, demand, or "
        "applications to the event."
    ),
    normalization="Return key market names in lower case.",
    rationale="Explain the alert evidence for the affected market.",
    edge_cases=(
        "If a phrase is broad industry context, put it in sectors instead of "
        "key_markets."
    ),
)

commodities_prompt = _field_prompt(
    field="commodities",
    purpose="Extract physical inputs whose availability, pricing, or supply matters.",
    include=(
        "Raw materials, traded goods, industrial inputs, components, chips, "
        "magnets, bearings, motors, or other physical supply items."
    ),
    exclude=(
        "Broad industries, end markets, regulators, companies, macro drivers, and "
        "themes."
    ),
    evidence=(
        "Include a commodity or component when the alert links it to supply, cost, "
        "pricing, availability, production, or demand."
    ),
    normalization="Return commodity and component names in lower case.",
    rationale="Explain the text evidence for why the input matters.",
    edge_cases=(
        "Treat components as commodities for this first pass when they create "
        "supply, cost, or production exposure."
    ),
)

regulators_prompt = _field_prompt(
    field="regulators",
    purpose="Extract regulatory bodies, laws, regimes, or formal review processes.",
    include=(
        "Agencies, laws, enforcement regimes, export controls, national security "
        "reviews, compliance processes, and formal regulatory actions."
    ),
    exclude=(
        "Generic government mentions, countries without regulatory action, "
        "political themes, macro risks, and company names."
    ),
    evidence=(
        "Include a regulator or regime when the alert names it or clearly describes "
        "a formal regulatory action."
    ),
    normalization="Return regulator and regime names in lower case.",
    rationale="Explain the regulatory evidence and why it matters.",
    edge_cases=(
        "Use geo_markets for countries unless the country reference is tied to a "
        "specific regulatory action."
    ),
)

macro_sensitivities_prompt = _field_prompt(
    field="macro_sensitivities",
    purpose="Extract broad economic or geopolitical drivers affecting the alert.",
    include=(
        "Interest rates, tariffs, reshoring, labor costs, trade restrictions, "
        "geopolitical risk, financing conditions, inflation, or demand cycles."
    ),
    exclude=(
        "Specific companies, sectors, product markets, countries without macro "
        "driver relevance, commodities, and regulators."
    ),
    evidence=(
        "Include a macro sensitivity when the alert links it to valuation, demand, "
        "margins, financing, operations, or supply chains."
    ),
    normalization="Return macro sensitivity names in lower case.",
    rationale="Explain the economic or geopolitical exposure in the alert.",
    edge_cases=(
        "Do not infer a macro driver just because a company is in a cyclical "
        "sector; require alert evidence."
    ),
)

themes_prompt = _field_prompt(
    field="themes",
    purpose="Extract strategic or investment themes explaining why the alert matters.",
    include=(
        "Themes such as AI-driven automation, labor shortage, supply chain "
        "resilience, nearshoring, productivity gains, or vertical integration."
    ),
    exclude=(
        "Literal company names, countries, regulators, sectors, narrow markets, "
        "commodities, and one-off facts that do not generalize."
    ),
    evidence=(
        "Include a theme when the alert supports a broader strategic or investment "
        "interpretation beyond a single fact."
    ),
    normalization="Return theme names in lower case.",
    rationale="Explain the alert evidence supporting the theme.",
    edge_cases=(
        "Prefer macro_sensitivities for economic drivers and key_markets for "
        "specific demand pools."
    ),
)

FIELD_PROMPT_SECTIONS = {
    "companies": companies_prompt,
    "sectors": sectors_prompt,
    "geo_markets": geo_markets_prompt,
    "key_markets": key_markets_prompt,
    "commodities": commodities_prompt,
    "regulators": regulators_prompt,
    "macro_sensitivities": macro_sensitivities_prompt,
    "themes": themes_prompt,
}

GLOBAL_EXTRACTION_RULES = (
    "Do not hallucinate facts that are absent from the subject or body.",
    "Return lower-case names for all extracted companies and metadata items.",
    "Return lower-case tickers when present; use null when unavailable.",
    "Return an empty array when a field has no supported values.",
    "Keep rationales concise and grounded in alert evidence.",
    "Do not canonicalize aliases or map values to stable internal identifiers.",
)


def format_context_hints(
    context_hints: Mapping[str, object] | None = None,
) -> str:
    """Format optional context values as prompt hints.

    Args:
        context_hints (Mapping[str, object] | None): Optional context values
            that guide extraction without acting as closed allowlists.

    Returns:
        str: Human-readable prompt text for the supplied hints, or an explicit
        missing-context message.
    """

    if not context_hints:
        return "none provided"

    lines = [
        "context only; not closed allowlists",
    ]
    for key in sorted(context_hints):
        lines.append(f"- {key}: {_format_hint_value(context_hints[key])}")
    return "\n".join(lines)


def build_synthesis_prompt(
    subject: str,
    body: str,
    context_hints: Mapping[str, object] | None = None,
) -> str:
    """Build the final model-facing extraction prompt for one alert.

    Args:
        subject (str): Raw alert subject or headline.
        body (str): Raw alert body text.
        context_hints (Mapping[str, object] | None): Optional context values
            to include in the prompt.

    Returns:
        str: Complete prompt sent to the extraction model.
    """

    prompt_sections = "\n\n".join(
        _xml_element(
            tag="prompt_section",
            content=FIELD_PROMPT_SECTIONS[field],
            attributes={"name": field},
        )
        for field in AI_EXTRACTED_FIELDS
    )
    global_rules = "\n".join(f"- {rule}" for rule in GLOBAL_EXTRACTION_RULES)

    return "\n\n".join(
        (
            EXTRACTION_PERSONA,
            _news_block(subject=subject, body=body),
            _xml_element(
                tag="context_hints",
                content=format_context_hints(context_hints),
            ),
            _xml_element(tag="global_rules", content=global_rules),
            "<prompt_sections>",
            prompt_sections,
            "</prompt_sections>",
        )
    )


def _format_hint_value(value: object) -> str:
    """Format one context hint value for prompt inclusion.

    Args:
        value (object): Raw context hint value.

    Returns:
        str: Prompt-safe string representation of the hint value.
    """

    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return json.dumps(value, sort_keys=True)
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(item) for item in value)
    return str(value)


def _news_block(subject: str, body: str) -> str:
    """Format alert content inside XML-style tags.

    Args:
        subject (str): Raw alert subject or headline.
        body (str): Raw alert body text.

    Returns:
        str: XML-style prompt block containing escaped alert content.
    """

    return "\n".join(
        (
            "<news>",
            _xml_element(tag="subject", content=subject),
            _xml_element(tag="body", content=body),
            "</news>",
        )
    )


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
    "AI_EXTRACTED_FIELDS",
    "FIELD_PROMPT_SECTIONS",
    "GLOBAL_EXTRACTION_RULES",
    "EXTRACTION_PERSONA",
    "OUTPUT_FIELDS",
    "OUTPUT_FIELD_SEMANTICS",
    "SOURCE_FIELDS",
    "build_synthesis_prompt",
    "commodities_prompt",
    "companies_prompt",
    "format_context_hints",
    "geo_markets_prompt",
    "key_markets_prompt",
    "macro_sensitivities_prompt",
    "regulators_prompt",
    "sectors_prompt",
    "themes_prompt",
]

"""Pydantic schemas for raw and enriched ETL records."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RawAlert(BaseModel):
    """Source alert record loaded from the raw alert dataset."""

    id: str = Field(
        description="Source alert identifier copied unchanged from the input dataset.",
    )
    received_at: str = Field(
        description=(
            "Source alert receipt timestamp copied unchanged from the input dataset."
        ),
    )
    subject: str = Field(
        description=(
            "Source alert subject or headline copied unchanged from the input dataset."
        ),
    )
    body: str = Field(
        description="Source alert body text copied unchanged from the input dataset.",
    )


class CompanyItem(BaseModel):
    """First-pass extracted company metadata item."""

    name: str = Field(
        description=(
            "Lower-case named business entity relevant to the alert, such as a "
            "focal company, competitor, supplier, customer, partner, acquirer, "
            "acquisition target, or other operating business."
        ),
    )
    ticker: str | None = Field(
        default=None,
        description=(
            "Lower-case ticker when explicitly present or highly confident from "
            "alert context; null when unavailable."
        ),
    )
    rationale: str = Field(
        description=(
            "Concise alert-grounded evidence explaining why the company was included."
        ),
    )


class MetadataItem(BaseModel):
    """First-pass extracted non-company metadata item."""

    name: str = Field(
        description="Lower-case extracted metadata value supported by the alert text.",
    )
    rationale: str = Field(
        description=(
            "Concise alert-grounded evidence explaining why the item was included."
        ),
    )


class AlertMetadata(BaseModel):
    """First-pass metadata extracted by the AI model for one alert."""

    companies: list[CompanyItem] = Field(
        default_factory=list,
        description=(
            "Named business entities relevant to the alert. Excludes countries, "
            "regulators, markets, sectors, commodities, themes, and macro concepts."
        ),
    )
    sectors: list[MetadataItem] = Field(
        default_factory=list,
        description=(
            "Broad industries or business verticals affected by the alert; broader "
            "than a single company and distinct from customer or end markets when "
            "possible."
        ),
    )
    geo_markets: list[MetadataItem] = Field(
        default_factory=list,
        description=(
            "Countries or regions materially connected to operations, demand, "
            "supply chains, regulation, investment, or manufacturing in the alert."
        ),
    )
    key_markets: list[MetadataItem] = Field(
        default_factory=list,
        description=(
            "Product markets, end markets, customer markets, or demand pools "
            "affected by the alert."
        ),
    )
    commodities: list[MetadataItem] = Field(
        default_factory=list,
        description=(
            "Raw materials, traded goods, physical inputs, or components whose "
            "availability, pricing, or supply affects the alert."
        ),
    )
    regulators: list[MetadataItem] = Field(
        default_factory=list,
        description=(
            "Regulatory bodies, laws, agencies, enforcement regimes, or formal "
            "review processes mentioned or clearly implicated by the alert."
        ),
    )
    macro_sensitivities: list[MetadataItem] = Field(
        default_factory=list,
        description=(
            "Broad economic or geopolitical drivers that can affect valuation, "
            "demand, margins, financing, or supply chains."
        ),
    )
    themes: list[MetadataItem] = Field(
        default_factory=list,
        description=(
            "Strategic or investment themes that summarize why the alert matters "
            "across companies or markets."
        ),
    )


class EnrichedAlert(RawAlert, AlertMetadata):
    """Raw alert record combined with first-pass structured metadata."""


__all__ = [
    "AlertMetadata",
    "CompanyItem",
    "EnrichedAlert",
    "MetadataItem",
    "RawAlert",
]

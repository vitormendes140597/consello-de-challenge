"""Shared ETL field name constants."""

SOURCE_FIELDS = ("id", "received_at", "subject", "body")
AI_EXTRACTED_FIELDS = (
    "companies",
    "sectors",
    "geo_markets",
    "key_markets",
    "commodities",
    "regulators",
    "macro_sensitivities",
    "themes",
)
OUTPUT_FIELDS = SOURCE_FIELDS + AI_EXTRACTED_FIELDS
CANONICAL_FIELDS = AI_EXTRACTED_FIELDS
METADATA_FIELDS = tuple(field for field in AI_EXTRACTED_FIELDS if field != "companies")

__all__ = [
    "AI_EXTRACTED_FIELDS",
    "CANONICAL_FIELDS",
    "METADATA_FIELDS",
    "OUTPUT_FIELDS",
    "SOURCE_FIELDS",
]

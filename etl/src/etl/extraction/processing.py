"""ETL processing orchestration for alert extraction."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor

from etl.common.config import ETLConfig
from etl.common.io import AlertDataLoader, JsonRecordStore, StorageBackend
from etl.common.schemas import EnrichedAlert, RawAlert
from etl.extraction.model import StructuredOutputModel, extract_alert_metadata
from etl.extraction.postprocessing import build_enriched_alert

ALERT_EXTRACTION_WORKERS = 20


def enrich_alert(
    alert: RawAlert,
    model: StructuredOutputModel,
    context_hints: Mapping[str, object] | None = None,
) -> EnrichedAlert:
    """Extract and attach first-pass metadata for one raw alert.

    Args:
        alert (RawAlert): Validated raw source alert.
        model (StructuredOutputModel): Structured-output-capable model used for
            AI extraction.
        context_hints (Mapping[str, object] | None): Optional client profile
            context values to include in the extraction prompt.

    Returns:
        EnrichedAlert: Source alert fields plus normalized extracted metadata.

    Raises:
        pydantic.ValidationError: If model output does not validate as alert
            metadata or enriched alert output.
    """

    metadata = extract_alert_metadata(
        alert=alert,
        model=model,
        context_hints=context_hints,
    )
    return build_enriched_alert(alert=alert, metadata=metadata)


def enrich_alerts(
    alerts: Sequence[RawAlert],
    model: StructuredOutputModel,
    context_hints: Mapping[str, object] | None = None,
) -> list[EnrichedAlert]:
    """Extract and attach first-pass metadata for each raw alert.

    Args:
        alerts (Sequence[RawAlert]): Validated source alerts.
        model (StructuredOutputModel): Structured-output-capable model used for
            AI extraction.
        context_hints (Mapping[str, object] | None): Optional client profile
            context values to include in extraction prompts.

    Returns:
        list[EnrichedAlert]: One enriched alert for each input alert, in input
        order.

    Raises:
        pydantic.ValidationError: If any model output does not validate as alert
            metadata or enriched alert output.
    """

    with ThreadPoolExecutor(max_workers=ALERT_EXTRACTION_WORKERS) as executor:
        return list(
            executor.map(
                lambda alert: enrich_alert(
                    alert=alert,
                    model=model,
                    context_hints=context_hints,
                ),
                alerts,
            )
        )


def run_alert_extraction_etl(
    config: ETLConfig,
    model: StructuredOutputModel,
) -> list[EnrichedAlert]:
    """Run the alert extraction ETL from configured JSON files.

    Args:
        config (ETLConfig): File path configuration for raw input, client
            profile context, and processed output.
        model (StructuredOutputModel): Structured-output-capable model used for
            AI extraction.

    Returns:
        list[EnrichedAlert]: Enriched alerts produced for the current run.

    Raises:
        OSError: If input files cannot be read or the output file cannot be
            written.
        json.JSONDecodeError: If an input file is not valid JSON.
        ValueError: If either input JSON root has the wrong shape.
        pydantic.ValidationError: If raw alerts or model outputs fail
            validation.
    """

    storage = StorageBackend()
    loader = AlertDataLoader(storage=storage)
    raw_alerts = loader.load_raw_alerts(config.input_path)
    # context_hints = loader.load_client_profile_context(config.client_profile_path)
    enriched_alerts = enrich_alerts(
        alerts=raw_alerts,
        model=model,
        # context_hints=context_hints,
    )
    JsonRecordStore(path=config.output_path, storage=storage).merge_records(
        enriched_alerts
    )
    return enriched_alerts


__all__ = [
    "enrich_alert",
    "enrich_alerts",
    "run_alert_extraction_etl",
]

"""JSON IO helpers for alert extraction ETL data boundaries."""

from __future__ import annotations

import json
from collections.abc import Hashable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeAlias, cast

from pydantic import BaseModel

from etl.common.schemas import EnrichedAlert, RawAlert

JsonRecord: TypeAlias = dict[str, object]
RecordInput: TypeAlias = BaseModel | Mapping[str, object]


class StorageBackend:
    """JSON file storage backend.

    This class is intentionally unaware of alert schemas. It only handles JSON
    reads and writes at filesystem boundaries.
    """

    def read_json(self, path: Path | str) -> object:
        """Read and decode a JSON file.

        Args:
            path (Path | str): JSON file path.

        Returns:
            object: Decoded JSON value.

        Raises:
            OSError: If the file cannot be read.
            json.JSONDecodeError: If the file is not valid JSON.
        """

        with Path(path).open(encoding="utf-8") as input_file:
            return json.load(input_file)

    def write_json(self, path: Path | str, data: object) -> None:
        """Write a JSON value to a file.

        Args:
            path (Path | str): Output JSON file path.
            data (object): JSON-serializable value to write.

        Returns:
            None: This method writes the JSON file.

        Raises:
            OSError: If the output directory cannot be created or the file
                cannot be written.
            TypeError: If ``data`` is not JSON serializable.
        """

        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = output_path.with_name(f".{output_path.name}.tmp")
        with temp_path.open("w", encoding="utf-8") as output_file:
            json.dump(data, output_file, indent=2)
            output_file.write("\n")
        temp_path.replace(output_path)


@dataclass(frozen=True)
class JsonRecordStore:
    """Single-file JSON array store that merges records by id.

    Attributes:
        path (Path | str): JSON array file managed by the store.
        id_field (str): Record field used as the merge key.
        storage (StorageBackend): Backend used for JSON file access.
    """

    path: Path | str
    id_field: str = "id"
    storage: StorageBackend = field(default_factory=StorageBackend)

    def read_records(self) -> list[JsonRecord]:
        """Read stored records from the JSON array file.

        Returns:
            list[JsonRecord]: Stored JSON object records, or an empty list when
            the store file does not exist.

        Raises:
            OSError: If the store file cannot be read.
            json.JSONDecodeError: If the store file is not valid JSON.
            ValueError: If the store root is not an array of objects.
        """

        store_path = Path(self.path)
        if not store_path.exists():
            return []

        data = self.storage.read_json(store_path)
        if not isinstance(data, list):
            raise ValueError(f"JSON record store must be a JSON array: {store_path}")

        records: list[JsonRecord] = []
        for index, record in enumerate(data):
            if not isinstance(record, Mapping):
                raise ValueError(
                    f"Stored record at index {index} must be a JSON object"
                )
            records.append(dict(record))
        return records

    def merge_records(self, records: Sequence[RecordInput]) -> list[JsonRecord]:
        """Merge records into the store by id.

        Incoming records replace existing records with matching ids. Existing
        records with ids absent from the incoming set are preserved, and new
        incoming ids are appended.

        Args:
            records (Sequence[RecordInput]): Pydantic models or mappings to
                serialize and merge into the store.

        Returns:
            list[JsonRecord]: Complete merged record set written to storage.

        Raises:
            OSError: If the store file cannot be read or written.
            json.JSONDecodeError: If the store file is not valid JSON.
            ValueError: If the store root is malformed, an incoming record is
                missing the id field, or an id value cannot be used as a key.
            TypeError: If a serialized record is not JSON serializable.
        """

        merged_records = self.read_records()
        positions = self._index_records(merged_records)

        for record in records:
            serialized_record = self._serialize_record(record)
            record_id = self._require_record_id(serialized_record)
            position = positions.get(record_id)

            if position is None:
                positions[record_id] = len(merged_records)
                merged_records.append(serialized_record)
                continue

            merged_records[position] = serialized_record

        self.storage.write_json(path=self.path, data=merged_records)
        return merged_records

    def _index_records(self, records: list[JsonRecord]) -> dict[Hashable, int]:
        """Index existing records by id while preserving records without ids.

        Args:
            records (list[JsonRecord]): Existing records loaded from storage.

        Returns:
            dict[Hashable, int]: Record positions keyed by configured id field.

        Raises:
            ValueError: If an existing id value cannot be used as a key.
        """

        positions: dict[Hashable, int] = {}
        for index, record in enumerate(records):
            if self.id_field not in record:
                continue

            record_id = self._validate_record_id(record[self.id_field])
            positions[record_id] = index
        return positions

    def _serialize_record(self, record: RecordInput) -> JsonRecord:
        """Serialize one Pydantic model or mapping into a JSON object.

        Args:
            record (RecordInput): Pydantic model or mapping record.

        Returns:
            JsonRecord: Serialized record dictionary.
        """

        if isinstance(record, BaseModel):
            return cast(JsonRecord, record.model_dump(mode="json"))
        return dict(record)

    def _require_record_id(self, record: JsonRecord) -> Hashable:
        """Read and validate the configured id field from one record.

        Args:
            record (JsonRecord): Serialized incoming record.

        Returns:
            Hashable: Id value used as the merge key.

        Raises:
            ValueError: If the id field is missing or cannot be used as a key.
        """

        if self.id_field not in record:
            raise ValueError(f"Incoming record is missing id field: {self.id_field}")
        return self._validate_record_id(record[self.id_field])

    def _validate_record_id(self, record_id: object) -> Hashable:
        """Validate a record id can be used as a dictionary key.

        Args:
            record_id (object): Record id value.

        Returns:
            Hashable: Validated hashable record id.

        Raises:
            ValueError: If the id value is not hashable.
        """

        if not isinstance(record_id, Hashable):
            raise ValueError(f"Record id must be hashable: {self.id_field}")
        return record_id


@dataclass(frozen=True)
class AlertDataLoader:
    """Alert ETL loader for schema validation around decoded JSON data.

    Attributes:
        storage (StorageBackend): Backend used for JSON file access.
    """

    storage: StorageBackend = field(default_factory=StorageBackend)

    def iter_raw_alerts(self, path: Path | str) -> Iterator[RawAlert]:
        """Yield validated raw alerts from a JSON array file.

        Args:
            path (Path | str): File path containing a JSON array of raw alert
                objects.

        Yields:
            RawAlert: Validated raw alert records.

        Raises:
            OSError: If the input file cannot be read.
            json.JSONDecodeError: If the input file is not valid JSON.
            ValueError: If the JSON root is not an array of objects.
            pydantic.ValidationError: If any raw alert is missing required
                fields or has invalid field values.
        """

        raw_data = self.storage.read_json(path)
        if not isinstance(raw_data, list):
            raise ValueError(f"Raw alert dataset must be a JSON array: {path}")

        for index, raw_record in enumerate(raw_data):
            if not isinstance(raw_record, Mapping):
                raise ValueError(f"Raw alert at index {index} must be a JSON object")
            yield RawAlert.model_validate(raw_record)

    def load_raw_alerts(self, path: Path | str) -> list[RawAlert]:
        """Load and validate raw alerts from a JSON array file.

        Args:
            path (Path | str): File path containing a JSON array of raw alert
                objects.

        Returns:
            list[RawAlert]: Validated raw alert records.

        Raises:
            OSError: If the input file cannot be read.
            json.JSONDecodeError: If the input file is not valid JSON.
            ValueError: If the JSON root is not an array of objects.
            pydantic.ValidationError: If any raw alert is missing required
                fields or has invalid field values.
        """

        return list(self.iter_raw_alerts(path))

    def iter_enriched_alerts(self, path: Path | str) -> Iterator[EnrichedAlert]:
        """Yield validated enriched alerts from a JSON array file.

        Args:
            path (Path | str): File path containing a JSON array of enriched
                alert objects.

        Yields:
            EnrichedAlert: Validated enriched alert records.

        Raises:
            OSError: If the input file cannot be read.
            json.JSONDecodeError: If the input file is not valid JSON.
            ValueError: If the JSON root is not an array of objects.
            pydantic.ValidationError: If any enriched alert is missing required
                fields or has invalid metadata.
        """

        enriched_data = self.storage.read_json(path)
        if not isinstance(enriched_data, list):
            raise ValueError(f"Enriched alert dataset must be a JSON array: {path}")

        for index, enriched_record in enumerate(enriched_data):
            if not isinstance(enriched_record, Mapping):
                raise ValueError(
                    f"Enriched alert at index {index} must be a JSON object"
                )
            yield EnrichedAlert.model_validate(enriched_record)

    def load_enriched_alerts(self, path: Path | str) -> list[EnrichedAlert]:
        """Load and validate enriched alerts from a JSON array file.

        Args:
            path (Path | str): File path containing a JSON array of enriched
                alert objects.

        Returns:
            list[EnrichedAlert]: Validated enriched alert records.

        Raises:
            OSError: If the input file cannot be read.
            json.JSONDecodeError: If the input file is not valid JSON.
            ValueError: If the JSON root is not an array of objects.
            pydantic.ValidationError: If any enriched alert is missing required
                fields or has invalid metadata.
        """

        return list(self.iter_enriched_alerts(path))

    def load_client_profile_context(self, path: Path | str) -> Mapping[str, object]:
        """Load client profile context hints from a JSON object file.

        Args:
            path (Path | str): File path containing a JSON object with profile
                values to pass as contextual hints.

        Returns:
            Mapping[str, object]: Client profile context values.

        Raises:
            OSError: If the context file cannot be read.
            json.JSONDecodeError: If the context file is not valid JSON.
            ValueError: If the JSON root is not an object.
        """

        data = self.storage.read_json(path)
        if not isinstance(data, Mapping):
            raise ValueError(f"Client profile context must be a JSON object: {path}")
        return data


__all__ = [
    "AlertDataLoader",
    "JsonRecordStore",
    "StorageBackend",
]

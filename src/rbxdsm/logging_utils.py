"""Run state persistence (for resumability) and logging setup."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .models import EntryRecord, EntryStatus


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def new_state_path(directory: str = ".") -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path(directory) / f"rbxdsm_state_{stamp}.json"


class StateStore:
    """Tracks per-entry migration status and persists it to a JSON file
    after every write, so a run can be safely resumed if interrupted."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._records: dict[str, EntryRecord] = {}
        if self.path.exists():
            self._load()

    @staticmethod
    def _record_key(datastore: str, scope: str, key: str) -> str:
        return f"{datastore}\x1f{scope}\x1f{key}"

    def _load(self) -> None:
        data = json.loads(self.path.read_text())
        for item in data.get("records", []):
            rec = EntryRecord.from_dict(item)
            self._records[self._record_key(rec.datastore, rec.scope, rec.key)] = rec

    def get(self, datastore: str, scope: str, key: str) -> EntryRecord | None:
        return self._records.get(self._record_key(datastore, scope, key))

    def upsert(self, record: EntryRecord) -> None:
        self._records[
            self._record_key(record.datastore, record.scope, record.key)
        ] = record
        self._flush()

    def pending_or_failed(self) -> Iterable[EntryRecord]:
        return [
            r
            for r in self._records.values()
            if r.status in (EntryStatus.PENDING, EntryStatus.FAILED)
        ]

    def all_records(self) -> Iterable[EntryRecord]:
        return list(self._records.values())

    def _flush(self) -> None:
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "records": [r.to_dict() for r in self._records.values()],
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        tmp.replace(self.path)

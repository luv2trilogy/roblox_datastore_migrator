"""Run state persistence (for resumability) and logging setup."""

from __future__ import annotations

import json
import logging
import os
import time
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

    def upsert(self, record: EntryRecord, flush: bool = True) -> None:
        self._records[
            self._record_key(record.datastore, record.scope, record.key)
        ] = record
        if flush:
            self._flush()

    def upsert_many(self, records: Iterable[EntryRecord]) -> None:
        """Add/update several records with a single flush at the end.
        Used by discovery/planning to avoid one disk write per key."""
        for record in records:
            self.upsert(record, flush=False)
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

        last_exc: Exception | None = None
        for attempt in range(5):
            try:
                os.replace(tmp, self.path)
                return
            except PermissionError as exc:
                last_exc = exc
                time.sleep(0.1 * (attempt + 1))

        logging.getLogger("rbxdsm.state").warning(
            "Atomic replace failed after retries (%s); falling back to "
            "direct write for %s",
            last_exc,
            self.path,
        )
        self.path.write_text(json.dumps(payload, indent=2))
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
"""Dataclasses shared across the migrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class EntryStatus(str, Enum):
    PENDING = "pending"
    COPIED = "copied"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class DataStoreRef:
    """Identifies a single DataStore, optionally scoped."""

    name: str
    scope: str = "global"

    def __str__(self) -> str:
        return f"{self.name}/{self.scope}" if self.scope != "global" else self.name


@dataclass
class EntryRecord:
    """Tracks the migration status of a single key within a DataStore."""

    datastore: str
    scope: str
    key: str
    status: EntryStatus = EntryStatus.PENDING
    error: Optional[str] = None
    attempts: int = 0
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def mark(self, status: EntryStatus, error: Optional[str] = None) -> None:
        self.status = status
        self.error = error
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "datastore": self.datastore,
            "scope": self.scope,
            "key": self.key,
            "status": self.status.value,
            "error": self.error,
            "attempts": self.attempts,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EntryRecord":
        return cls(
            datastore=data["datastore"],
            scope=data.get("scope", "global"),
            key=data["key"],
            status=EntryStatus(data.get("status", "pending")),
            error=data.get("error"),
            attempts=data.get("attempts", 0),
            updated_at=data.get("updated_at", ""),
        )


@dataclass
class MigrationSummary:
    total: int = 0
    copied: int = 0
    skipped: int = 0
    failed: int = 0

    def as_line(self) -> str:
        return (
            f"total={self.total} copied={self.copied} "
            f"skipped={self.skipped} failed={self.failed}"
        )

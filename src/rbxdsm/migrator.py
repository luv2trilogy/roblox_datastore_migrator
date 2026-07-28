"""Orchestrates the copy of entries from source to destination universe."""

from __future__ import annotations

import logging

from .client import OpenCloudClient, OpenCloudError
from .discovery import discover_datastores, discover_entries
from .logging_utils import StateStore
from .models import EntryRecord, EntryStatus, MigrationSummary

logger = logging.getLogger("rbxdsm.migrator")


class Migrator:
    def __init__(
        self,
        source_client: OpenCloudClient,
        dest_client: OpenCloudClient,
        state: StateStore,
        dry_run: bool = False,
        scope: str = "global",
        datastore_prefix: str = "",
        key_prefix: str = "",
    ):
        self.source = source_client
        self.dest = dest_client
        self.state = state
        self.dry_run = dry_run
        self.scope = scope
        self.datastore_prefix = datastore_prefix
        self.key_prefix = key_prefix

    def plan(self) -> list[tuple[str, str]]:
        """Discover (datastore, key) pairs to migrate. Populates state
        with PENDING records for anything not already tracked."""
        datastores = discover_datastores(self.source, prefix=self.datastore_prefix)
        if not datastores:
            logger.warning("No datastores discovered in source universe.")
            return []

        pairs: list[tuple[str, str]] = []
        new_records: list[EntryRecord] = []
        for ds_ref, key in discover_entries(
            self.source, datastores, scope=self.scope, key_prefix=self.key_prefix
        ):
            existing = self.state.get(ds_ref.name, ds_ref.scope, key)
            if existing is None:
                new_records.append(
                    EntryRecord(datastore=ds_ref.name, scope=ds_ref.scope, key=key)
                )
            pairs.append((ds_ref.name, key))

        if new_records:
            self.state.upsert_many(new_records)

        return pairs

    def run(self, pairs: list[tuple[str, str]] | None = None) -> MigrationSummary:
        """Copy each planned entry. If pairs is None, uses everything
        currently PENDING or FAILED in state (used by both `migrate`
        and `resume`)."""
        if pairs is None:
            targets = list(self.state.pending_or_failed())
        else:
            targets = []
            for ds_name, key in pairs:
                rec = self.state.get(ds_name, self.scope, key)
                if rec is None:
                    rec = EntryRecord(datastore=ds_name, scope=self.scope, key=key)
                if rec.status in (EntryStatus.PENDING, EntryStatus.FAILED):
                    targets.append(rec)

        summary = MigrationSummary(total=len(targets))

        for rec in targets:
            rec.attempts += 1
            try:
                value = self.source.get_entry(rec.datastore, rec.key, scope=rec.scope)
            except OpenCloudError as exc:
                logger.error("READ FAIL  %s/%s: %s", rec.datastore, rec.key, exc)
                rec.mark(EntryStatus.FAILED, error=f"read: {exc}")
                self.state.upsert(rec)
                summary.failed += 1
                continue

            if self.dry_run:
                logger.info("DRY-RUN    would copy %s/%s", rec.datastore, rec.key)
                rec.mark(EntryStatus.SKIPPED, error="dry-run")
                self.state.upsert(rec)
                summary.skipped += 1
                continue

            try:
                self.dest.set_entry(rec.datastore, rec.key, value, scope=rec.scope)
            except OpenCloudError as exc:
                logger.error("WRITE FAIL %s/%s: %s", rec.datastore, rec.key, exc)
                rec.mark(EntryStatus.FAILED, error=f"write: {exc}")
                self.state.upsert(rec)
                summary.failed += 1
                continue

            logger.info("COPIED     %s/%s", rec.datastore, rec.key)
            rec.mark(EntryStatus.COPIED)
            self.state.upsert(rec)
            summary.copied += 1

        return summary
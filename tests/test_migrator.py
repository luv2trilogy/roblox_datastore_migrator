import json
from pathlib import Path

import responses

from rbxdsm.client import OpenCloudClient
from rbxdsm.logging_utils import StateStore
from rbxdsm.migrator import Migrator

SRC_UNI = "1111"
DST_UNI = "2222"
SRC_BASE = f"https://apis.roblox.com/datastores/v1/universes/{SRC_UNI}"
DST_BASE = f"https://apis.roblox.com/datastores/v1/universes/{DST_UNI}"


def make_clients():
    src = OpenCloudClient(SRC_UNI, "src-key", max_retries=2)
    dst = OpenCloudClient(DST_UNI, "dst-key", max_retries=2)
    return src, dst


def mock_full_source(datastore="PlayerData", keys=("user_1", "user_2")):
    responses.add(
        responses.GET,
        f"{SRC_BASE}/standard-datastores",
        json={"datastores": [{"name": datastore}], "nextPageCursor": None},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{SRC_BASE}/standard-datastores/datastore/entries",
        json={"keys": [{"key": k} for k in keys], "nextPageCursor": None},
        status=200,
    )
    for k in keys:
        responses.add(
            responses.GET,
            f"{SRC_BASE}/standard-datastores/datastore/entries/entry",
            json={"key": k, "coins": 10},
            status=200,
        )


@responses.activate
def test_plan_and_run_full_migration(tmp_path: Path):
    mock_full_source()
    for _ in range(2):
        responses.add(
            responses.POST,
            f"{DST_BASE}/standard-datastores/datastore/entries/entry",
            json={"version": "v1"},
            status=200,
        )

    src, dst = make_clients()
    state = StateStore(tmp_path / "state.json")
    migrator = Migrator(src, dst, state)

    pairs = migrator.plan()
    assert len(pairs) == 2

    summary = migrator.run(pairs)
    assert summary.copied == 2
    assert summary.failed == 0

    saved = json.loads((tmp_path / "state.json").read_text())
    statuses = {r["key"]: r["status"] for r in saved["records"]}
    assert statuses == {"user_1": "copied", "user_2": "copied"}


@responses.activate
def test_dry_run_does_not_write(tmp_path: Path):
    mock_full_source(keys=("user_1",))
    # No POST mock registered - if the migrator tried to write, this would fail.

    src, dst = make_clients()
    state = StateStore(tmp_path / "state.json")
    migrator = Migrator(src, dst, state, dry_run=True)

    pairs = migrator.plan()
    summary = migrator.run(pairs)
    assert summary.skipped == 1
    assert summary.copied == 0


@responses.activate
def test_resume_only_retries_failed(tmp_path: Path):
    mock_full_source(keys=("user_1", "user_2"))
    # First dest write fails, second succeeds
    responses.add(
        responses.POST,
        f"{DST_BASE}/standard-datastores/datastore/entries/entry",
        status=500,
    )
    responses.add(
        responses.POST,
        f"{DST_BASE}/standard-datastores/datastore/entries/entry",
        status=500,
    )
    responses.add(
        responses.POST,
        f"{DST_BASE}/standard-datastores/datastore/entries/entry",
        json={"version": "v1"},
        status=200,
    )

    src, dst = make_clients()
    state_path = tmp_path / "state.json"
    state = StateStore(state_path)
    migrator = Migrator(src, dst, state)

    pairs = migrator.plan()
    summary = migrator.run(pairs)
    assert summary.copied == 1
    assert summary.failed == 1

    # Simulate resume: reload state, re-run only pending/failed
    responses.add(
        responses.GET,
        f"{SRC_BASE}/standard-datastores/datastore/entries/entry",
        json={"key": "user_2", "coins": 10},
        status=200,
    )
    responses.add(
        responses.POST,
        f"{DST_BASE}/standard-datastores/datastore/entries/entry",
        json={"version": "v1"},
        status=200,
    )

    state2 = StateStore(state_path)
    migrator2 = Migrator(src, dst, state2)
    resumed_summary = migrator2.run(pairs=None)
    assert resumed_summary.total == 1
    assert resumed_summary.copied == 1

    final = json.loads(state_path.read_text())
    statuses = {r["key"]: r["status"] for r in final["records"]}
    assert statuses == {"user_1": "copied", "user_2": "copied"}

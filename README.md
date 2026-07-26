# rbxdsm — Roblox DataStore Migrator

A CLI tool for migrating DataStore entries between two Roblox experiences
(universes) via the [Open Cloud API](https://create.roblox.com/docs/cloud/reference/DataStore).

Built for the common "private tester build → public release" scenario:
copy all player data from a closed testing universe into the live game
before/at launch, without hand-rolling one-off scripts each time.

## Features

- **Auto-discovery** — walks `ListDataStores` + `ListEntries` on the source
  universe, so you don't need to hardcode DataStore names.
- **Dry-run mode** — reads everything and reports what *would* be copied
  without writing to the destination.
- **Resumable** — every run writes a timestamped JSON state file tracking
  per-key status (`pending` / `copied` / `skipped` / `failed`). If a run is
  interrupted or partially fails, `rbxdsm resume` retries only what didn't
  succeed.
- **Flexible credentials** — API keys and universe IDs can come from CLI
  flags, environment variables, a `.env` file, or a JSON config file
  (precedence: CLI > env > `.env` > config file).
- **Simple fixed retries** with `Retry-After` support for 429/5xx responses.

## Install

```bash
git clone <this-repo>
cd roblox_datastore_migrator
pip install -e .
```

Requires Python 3.10+.

## Setup: Open Cloud API keys

For **each** universe (source and destination):

1. Go to the [Creator Dashboard → Open Cloud → API Keys](https://create.roblox.com/dashboard/credentials)
2. Create a new key, scoped to that specific universe (not "all experiences")
3. Grant **Datastore API** access:
   - Source key: `datastore.objects:read`, `datastore.objects:list`
   - Destination key: `datastore.objects:read`, `datastore.objects:write`, `datastore.objects:list`
4. Copy the key immediately — it's shown once
5. Note the universe ID (Studio → Game Settings, or the number in the
   Creator Dashboard experience URL)

## Configuration

Copy `.env.example` to `.env` and fill in real values:

```bash
cp .env.example .env
```

```
RBXDSM_SOURCE_UNIVERSE=123456789
RBXDSM_SOURCE_KEY=your-source-open-cloud-api-key
RBXDSM_DEST_UNIVERSE=987654321
RBXDSM_DEST_KEY=your-dest-open-cloud-api-key
```

`.env` is gitignored — never commit real keys. Alternatively, pass
`--source-universe` / `--source-key` / `--dest-universe` / `--dest-key`
directly, set the `RBXDSM_*` env vars yourself, or use `--config path.json`:

```json
{
  "source": { "universe_id": "123456789", "api_key": "..." },
  "dest":   { "universe_id": "987654321", "api_key": "..." }
}
```

## Usage

**List DataStores in a universe** (sanity check before migrating):

```bash
rbxdsm list-datastores --side source
```

**Dry run** — see what would be copied, no writes:

```bash
rbxdsm migrate --dry-run
```

**Run the migration:**

```bash
rbxdsm migrate
```

This prints the path to a state file, e.g. `rbxdsm_state_20260726T140000Z.json`.
Keep it — it's how you resume.

**Resume after an interruption or partial failure:**

```bash
rbxdsm resume --state-file rbxdsm_state_20260726T140000Z.json
```

Only entries still marked `pending` or `failed` are retried; already-copied
entries are left alone.

### Scoping a migration

```bash
# Only migrate DataStores whose name starts with "Player"
rbxdsm migrate --datastore-prefix Player

# Only migrate keys matching a prefix within each DataStore
rbxdsm migrate --key-prefix user_

# Non-default scope (Roblox DataStores support scopes beyond "global")
rbxdsm migrate --scope global
```

## How it works

```
src/rbxdsm/
├── cli.py            CLI entrypoint (argparse subcommands: list-datastores, migrate, resume)
├── config.py          Resolves credentials: CLI flags > env vars > .env > config file
├── client.py           OpenCloudClient: list/get/set entries, pagination, fixed retries
├── discovery.py         Walks source universe to find DataStores + keys
├── migrator.py            Orchestrates read-from-source / write-to-dest, dry-run, resume
├── logging_utils.py        StateStore (resumable JSON state) + logging setup
└── models.py                 EntryRecord / MigrationSummary dataclasses
```

The core loop (`Migrator.run`) is intentionally simple: for each planned
`(datastore, key)` pair, read from source, optionally write to destination,
record the outcome to the state file immediately (so a crash mid-run loses
at most one entry's progress, not the whole run).

## Testing

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

Tests mock the Open Cloud API via `responses` — no real Roblox credentials
or network access needed. Covers pagination, retry/backoff behavior,
dry-run (asserts no write call is made), and resume (asserts only
failed/pending entries are retried, not already-copied ones).

## Limitations

- Standard DataStores only (no OrderedDataStore support in this version).
- No schema transformation — this tool does a direct value copy. If your
  source and destination schemas differ, write a transform step between
  `get_entry` and `set_entry` in `migrator.py`.
- Subject to Roblox's Open Cloud rate limits; large migrations may take a
  while and should be run with an eye on retry/failure counts.

## Disclaimer

Not affiliated with Roblox Corporation. Uses the public Open Cloud API.
Back up your DataStores before running a live migration — `--dry-run` first.

# rbxdsm

A Python CLI for migrating Roblox DataStore entries between two universes using the Roblox Open Cloud API.
## Features

- Automatic DataStore discovery
- Dry-run mode
- Resumable migrations
- Environment variable and config support
- Automatic retry handling

## Installation

```bash
git clone <repository>
cd rbxdsm
pip install -e .
```

Requires Python 3.10+.

## Configuration

Create a `.env` file:

```env
RBXDSM_SOURCE_UNIVERSE=123456789
RBXDSM_SOURCE_KEY=your-source-api-key

RBXDSM_DEST_UNIVERSE=987654321
RBXDSM_DEST_KEY=your-destination-api-key
```

You can also provide credentials through command line arguments or a JSON configuration file.

## Usage

List DataStores:

```bash
rbxdsm list-datastores --side source
```

Preview a migration:

```bash
rbxdsm migrate --dry-run
```

Run the migration:

```bash
rbxdsm migrate
```

Resume an interrupted migration:

```bash
rbxdsm resume --state-file rbxdsm_state_YYYYMMDDTHHMMSSZ.json
```

Filter by DataStore or key:

```bash
rbxdsm migrate --datastore-prefix Player

rbxdsm migrate --key-prefix user_
```

Specify a scope:

```bash
rbxdsm migrate --scope global
```

## Project Structure

```
src/rbxdsm/
├── cli.py
├── client.py
├── config.py
├── discovery.py
├── logging_utils.py
├── migrator.py
└── models.py
```

## Testing

Install development dependencies:

```bash
pip install -e ".[dev]"
```

Run the test suite:

```bash
pytest tests/ -v
```

## Limitations

- Standard DataStores only
- No automatic schema conversion
- Subject to Roblox Open Cloud rate limits

## Disclaimer

This project is not affiliated with Roblox Corporation.

Always perform a dry run and back up your DataStores before migrating production data.
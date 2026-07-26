"""Configuration resolution for API keys and universe IDs.

Precedence for any given value: explicit CLI flag > environment variable
> .env file (loaded into env if present) > config file (--config path,
JSON) > error.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class ConfigError(Exception):
    pass


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader; skips comments/blank lines, does not overwrite
    variables already set in the real environment."""
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass
class UniverseConfig:
    universe_id: str
    api_key: str


@dataclass
class MigratorConfig:
    source: UniverseConfig
    dest: UniverseConfig
    request_timeout: float = 30.0
    max_retries: int = 3


def _resolve(
    cli_value: Optional[str],
    env_var: str,
    file_data: dict,
    file_key: str,
) -> Optional[str]:
    if cli_value:
        return cli_value
    if os.environ.get(env_var):
        return os.environ[env_var]
    if file_key in file_data:
        return str(file_data[file_key])
    return None


def load_config(args) -> MigratorConfig:
    """Build a MigratorConfig from parsed CLI args, honoring the
    CLI > env > .env > config-file precedence."""

    
    
    dotenv_path = Path(getattr(args, "env_file", None) or ".env")
    _load_dotenv(dotenv_path)

    file_data: dict = {}
    config_path = getattr(args, "config", None)
    if config_path:
        path = Path(config_path)
        if not path.exists():
            raise ConfigError(f"Config file not found: {path}")
        try:
            file_data = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Invalid JSON in config file {path}: {exc}") from exc

    source_file = file_data.get("source", {})
    dest_file = file_data.get("dest", {})

    source_universe = _resolve(
        getattr(args, "source_universe", None),
        "RBXDSM_SOURCE_UNIVERSE",
        source_file,
        "universe_id",
    )
    source_key = _resolve(
        getattr(args, "source_key", None),
        "RBXDSM_SOURCE_KEY",
        source_file,
        "api_key",
    )
    dest_universe = _resolve(
        getattr(args, "dest_universe", None),
        "RBXDSM_DEST_UNIVERSE",
        dest_file,
        "universe_id",
    )
    dest_key = _resolve(
        getattr(args, "dest_key", None),
        "RBXDSM_DEST_KEY",
        dest_file,
        "api_key",
    )

    missing = [
        name
        for name, val in [
            ("source universe id", source_universe),
            ("source api key", source_key),
            ("dest universe id", dest_universe),
            ("dest api key", dest_key),
        ]
        if not val
    ]
    if missing:
        raise ConfigError(
            "Missing required config: "
            + ", ".join(missing)
            + ". Provide via CLI flags, RBXDSM_* env vars, a .env file, "
            "or --config JSON file."
        )

    return MigratorConfig(
        source=UniverseConfig(universe_id=source_universe, api_key=source_key),
        dest=UniverseConfig(universe_id=dest_universe, api_key=dest_key),
        request_timeout=getattr(args, "timeout", 30.0),
        max_retries=getattr(args, "max_retries", 3),
    )

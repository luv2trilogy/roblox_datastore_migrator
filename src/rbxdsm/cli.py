"""Command-line interface for rbxdsm."""

from __future__ import annotations

import argparse
import logging
import sys

from .client import OpenCloudClient, OpenCloudError
from .config import ConfigError, load_config
from .logging_utils import StateStore, new_state_path, setup_logging
from .migrator import Migrator

logger = logging.getLogger("rbxdsm.cli")


def _add_common_auth_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source-universe", help="Source universe ID")
    parser.add_argument(
        "--source-key", help="Source Open Cloud API key (or set RBXDSM_SOURCE_KEY)"
    )
    parser.add_argument("--dest-universe", help="Destination universe ID")
    parser.add_argument(
        "--dest-key", help="Destination Open Cloud API key (or set RBXDSM_DEST_KEY)"
    )
    parser.add_argument(
        "--config", help="Path to a JSON config file with source/dest credentials"
    )
    parser.add_argument(
        "--env-file", default=".env", help="Path to a .env file (default: ./.env)"
    )
    parser.add_argument(
        "--timeout", type=float, default=30.0, help="Per-request timeout in seconds"
    )
    parser.add_argument(
        "--max-retries", type=int, default=3, help="Fixed retry count per request"
    )
    parser.add_argument("-v", "--verbose", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rbxdsm",
        description=(
            "Migrate Roblox DataStore entries between experiences via the "
            "Open Cloud API."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser(
        "list-datastores", help="List DataStores visible in a universe"
    )
    _add_common_auth_args(p_list)
    p_list.add_argument(
        "--side",
        choices=["source", "dest"],
        default="source",
        help="Which configured universe to list (default: source)",
    )
    p_list.add_argument("--prefix", default="", help="Filter by name prefix")
    p_list.set_defaults(func=cmd_list_datastores)

    p_migrate = sub.add_parser(
        "migrate", help="Discover and copy all entries from source to dest"
    )
    _add_common_auth_args(p_migrate)
    p_migrate.add_argument(
        "--scope", default="global", help="DataStore scope (default: global)"
    )
    p_migrate.add_argument(
        "--datastore-prefix", default="", help="Only migrate DataStores matching prefix"
    )
    p_migrate.add_argument(
        "--key-prefix", default="", help="Only migrate keys matching prefix"
    )
    p_migrate.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover and read entries but do not write to destination",
    )
    p_migrate.add_argument(
        "--state-dir",
        default=".",
        help="Directory to write the run's state file into (default: cwd)",
    )
    p_migrate.set_defaults(func=cmd_migrate)

    p_resume = sub.add_parser(
        "resume", help="Resume a previous run from its state file"
    )
    _add_common_auth_args(p_resume)
    p_resume.add_argument(
        "--state-file", required=True, help="Path to the state file to resume"
    )
    p_resume.add_argument(
        "--scope", default="global", help="DataStore scope (default: global)"
    )
    p_resume.add_argument(
        "--dry-run",
        action="store_true",
        help="Re-attempt reads but do not write to destination",
    )
    p_resume.set_defaults(func=cmd_resume)

    return parser


def cmd_list_datastores(args) -> int:
    config = load_config(args)
    uni = config.source if args.side == "source" else config.dest
    client = OpenCloudClient(
        uni.universe_id,
        uni.api_key,
        timeout=config.request_timeout,
        max_retries=config.max_retries,
    )
    names = list(client.list_datastores(prefix=args.prefix))
    if not names:
        print("No datastores found.")
        return 0
    for name in names:
        print(name)
    return 0


def cmd_migrate(args) -> int:
    config = load_config(args)
    source_client = OpenCloudClient(
        config.source.universe_id,
        config.source.api_key,
        timeout=config.request_timeout,
        max_retries=config.max_retries,
    )
    dest_client = OpenCloudClient(
        config.dest.universe_id,
        config.dest.api_key,
        timeout=config.request_timeout,
        max_retries=config.max_retries,
    )

    state_path = new_state_path(args.state_dir)
    state = StateStore(state_path)
    logger.info("State file: %s", state_path)

    migrator = Migrator(
        source_client,
        dest_client,
        state,
        dry_run=args.dry_run,
        scope=args.scope,
        datastore_prefix=args.datastore_prefix,
        key_prefix=args.key_prefix,
    )

    logger.info("Discovering datastores and keys on source universe...")
    pairs = migrator.plan()
    logger.info("Found %d entr(y/ies) to migrate.", len(pairs))
    if not pairs:
        return 0

    if args.dry_run:
        logger.info("Dry run: no writes will be made.")

    summary = migrator.run(pairs)
    logger.info("Done. %s", summary.as_line())
    logger.info("State file for resume/audit: %s", state_path)
    return 1 if summary.failed else 0


def cmd_resume(args) -> int:
    config = load_config(args)
    source_client = OpenCloudClient(
        config.source.universe_id,
        config.source.api_key,
        timeout=config.request_timeout,
        max_retries=config.max_retries,
    )
    dest_client = OpenCloudClient(
        config.dest.universe_id,
        config.dest.api_key,
        timeout=config.request_timeout,
        max_retries=config.max_retries,
    )

    state = StateStore(args.state_file)
    pending = state.pending_or_failed()
    logger.info("Resuming %d pending/failed entr(y/ies) from %s", len(list(pending)), args.state_file)

    migrator = Migrator(
        source_client,
        dest_client,
        state,
        dry_run=args.dry_run,
        scope=args.scope,
    )
    summary = migrator.run(pairs=None)
    logger.info("Done. %s", summary.as_line())
    return 1 if summary.failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(verbose=getattr(args, "verbose", False))
    try:
        return args.func(args)
    except ConfigError as exc:
        logger.error(str(exc))
        return 2
    except OpenCloudError as exc:
        logger.error("Open Cloud API error: %s", exc)
        return 3
    except KeyboardInterrupt:
        logger.warning("Interrupted.")
        return 130


if __name__ == "__main__":
    sys.exit(main())

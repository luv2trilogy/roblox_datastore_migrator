"""Discovery of DataStores and keys on the source universe."""

from __future__ import annotations

import logging
from typing import Iterator

from .client import OpenCloudClient
from .models import DataStoreRef

logger = logging.getLogger("rbxdsm.discovery")


def discover_datastores(
    client: OpenCloudClient, prefix: str = ""
) -> list[str]:
    """Return all DataStore names visible in the source universe."""
    names = list(client.list_datastores(prefix=prefix))
    logger.info("Discovered %d datastore(s)", len(names))
    return names


def discover_entries(
    client: OpenCloudClient,
    datastore_names: list[str],
    scope: str = "global",
    key_prefix: str = "",
) -> Iterator[DataStoreRef]:
    """Yield (datastore, key) pairs across the given DataStores."""
    for name in datastore_names:
        count = 0
        for key in client.list_keys(name, scope=scope, prefix=key_prefix):
            count += 1
            yield DataStoreRef(name=name, scope=scope), key
        logger.info("  %s: %d key(s)", name, count)

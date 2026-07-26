"""Thin wrapper around the Roblox Open Cloud DataStore API v1.

Docs: https://create.roblox.com/docs/cloud/reference/DataStore
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Iterator, Optional

import requests

logger = logging.getLogger("rbxdsm.client")

BASE_URL = "https://apis.roblox.com/datastores/v1"


class OpenCloudError(Exception):
    """Raised for non-retryable or exhausted-retry API failures."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class OpenCloudClient:
    """Client for one universe. Create one per side (source/dest)."""

    def __init__(
        self,
        universe_id: str,
        api_key: str,
        timeout: float = 30.0,
        max_retries: int = 3,
        session: Optional[requests.Session] = None,
    ):
        self.universe_id = universe_id
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = session or requests.Session()

    def _headers(self) -> dict:
        return {"x-api-key": self.api_key}

    def _request(
        self, method: str, url: str, extra_headers: Optional[dict] = None, **kwargs
    ) -> requests.Response:
        """Issue a request with simple fixed-count retries.

        Retries on network errors and 429/5xx responses. Honors
        Retry-After when present, otherwise a flat 2s delay between
        attempts.
        """
        headers = self._headers()
        if extra_headers:
            headers.update(extra_headers)

        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.request(
                    method,
                    url,
                    headers=headers,
                    timeout=self.timeout,
                    **kwargs,
                )
            except requests.RequestException as exc:
                last_exc = exc
                logger.warning(
                    "Request error (attempt %d/%d): %s", attempt, self.max_retries, exc
                )
                time.sleep(2)
                continue

            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 2.0
                logger.warning(
                    "Got %d (attempt %d/%d), retrying in %.1fs",
                    resp.status_code,
                    attempt,
                    self.max_retries,
                    delay,
                )
                time.sleep(delay)
                last_exc = OpenCloudError(
                    f"HTTP {resp.status_code}: {resp.text[:300]}", resp.status_code
                )
                continue

            if not resp.ok:
                raise OpenCloudError(
                    f"HTTP {resp.status_code}: {resp.text[:300]}", resp.status_code
                )

            return resp

        raise OpenCloudError(
            f"Exhausted {self.max_retries} retries: {last_exc}"
        )

    
    
    

    def list_datastores(self, prefix: str = "") -> Iterator[str]:
        """Yield DataStore names for this universe."""
        cursor = None
        url = f"{BASE_URL}/universes/{self.universe_id}/standard-datastores"
        while True:
            params: dict[str, Any] = {"limit": 100}
            if prefix:
                params["prefix"] = prefix
            if cursor:
                params["cursor"] = cursor
            resp = self._request("GET", url, params=params)
            data = resp.json()
            for entry in data.get("datastores", []):
                yield entry["name"]
            cursor = data.get("nextPageCursor")
            if not cursor:
                break

    def list_keys(
        self, datastore_name: str, scope: str = "global", prefix: str = ""
    ) -> Iterator[str]:
        """Yield keys within a DataStore/scope."""
        cursor = None
        url = f"{BASE_URL}/universes/{self.universe_id}/standard-datastores/datastore/entries"
        while True:
            params: dict[str, Any] = {
                "datastoreName": datastore_name,
                "scope": scope,
                "limit": 100,
            }
            if prefix:
                params["prefix"] = prefix
            if cursor:
                params["cursor"] = cursor
            resp = self._request("GET", url, params=params)
            data = resp.json()
            for entry in data.get("keys", []):
                yield entry["key"]
            cursor = data.get("nextPageCursor")
            if not cursor:
                break

    
    
    

    def get_entry(
        self, datastore_name: str, key: str, scope: str = "global"
    ) -> Any:
        """Return the parsed JSON value stored at key."""
        url = f"{BASE_URL}/universes/{self.universe_id}/standard-datastores/datastore/entries/entry"
        params = {"datastoreName": datastore_name, "scope": scope, "entryKey": key}
        resp = self._request("GET", url, params=params)
        try:
            return resp.json()
        except json.JSONDecodeError:
            return resp.text

    def set_entry(
        self,
        datastore_name: str,
        key: str,
        value: Any,
        scope: str = "global",
    ) -> None:
        """Write value to key, overwriting any existing entry."""
        url = f"{BASE_URL}/universes/{self.universe_id}/standard-datastores/datastore/entries/entry"
        params = {"datastoreName": datastore_name, "scope": scope, "entryKey": key}
        self._request(
            "POST",
            url,
            params=params,
            data=json.dumps(value),
            extra_headers={"content-type": "application/json"},
        )

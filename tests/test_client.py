import responses

from rbxdsm.client import OpenCloudClient, OpenCloudError

UNIVERSE = "1111"
BASE = f"https://apis.roblox.com/datastores/v1/universes/{UNIVERSE}"


def make_client(**kwargs):
    return OpenCloudClient(UNIVERSE, "test-key", max_retries=2, **kwargs)


@responses.activate
def test_list_datastores_paginates():
    responses.add(
        responses.GET,
        f"{BASE}/standard-datastores",
        json={"datastores": [{"name": "PlayerData"}], "nextPageCursor": "abc"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE}/standard-datastores",
        json={"datastores": [{"name": "Inventory"}], "nextPageCursor": None},
        status=200,
    )
    client = make_client()
    names = list(client.list_datastores())
    assert names == ["PlayerData", "Inventory"]


@responses.activate
def test_list_keys_paginates():
    responses.add(
        responses.GET,
        f"{BASE}/standard-datastores/datastore/entries",
        json={"keys": [{"key": "user_1"}], "nextPageCursor": "xyz"},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE}/standard-datastores/datastore/entries",
        json={"keys": [{"key": "user_2"}], "nextPageCursor": None},
        status=200,
    )
    client = make_client()
    keys = list(client.list_keys("PlayerData"))
    assert keys == ["user_1", "user_2"]


@responses.activate
def test_get_entry_returns_json():
    responses.add(
        responses.GET,
        f"{BASE}/standard-datastores/datastore/entries/entry",
        json={"coins": 100, "level": 5},
        status=200,
    )
    client = make_client()
    value = client.get_entry("PlayerData", "user_1")
    assert value == {"coins": 100, "level": 5}


@responses.activate
def test_set_entry_sends_json_body():
    responses.add(
        responses.POST,
        f"{BASE}/standard-datastores/datastore/entries/entry",
        json={"version": "v1"},
        status=200,
    )
    client = make_client()
    client.set_entry("PlayerData", "user_1", {"coins": 100})

    sent = responses.calls[0].request
    assert sent.headers["content-type"] == "application/json"
    assert sent.headers["x-api-key"] == "test-key"
    body = sent.body if isinstance(sent.body, str) else sent.body.decode()
    assert '"coins": 100' in body


@responses.activate
def test_retries_on_429_then_succeeds():
    responses.add(
        responses.GET,
        f"{BASE}/standard-datastores/datastore/entries/entry",
        status=429,
        headers={"Retry-After": "0"},
    )
    responses.add(
        responses.GET,
        f"{BASE}/standard-datastores/datastore/entries/entry",
        json={"ok": True},
        status=200,
    )
    client = make_client()
    value = client.get_entry("PlayerData", "user_1")
    assert value == {"ok": True}
    assert len(responses.calls) == 2


@responses.activate
def test_exhausts_retries_and_raises():
    for _ in range(2):
        responses.add(
            responses.GET,
            f"{BASE}/standard-datastores/datastore/entries/entry",
            status=500,
        )
    client = make_client()
    try:
        client.get_entry("PlayerData", "user_1")
        assert False, "expected OpenCloudError"
    except OpenCloudError:
        pass


@responses.activate
def test_non_retryable_4xx_raises_immediately():
    responses.add(
        responses.GET,
        f"{BASE}/standard-datastores/datastore/entries/entry",
        status=404,
        body="entry not found",
    )
    client = make_client()
    try:
        client.get_entry("PlayerData", "missing_key")
        assert False, "expected OpenCloudError"
    except OpenCloudError as exc:
        assert exc.status_code == 404
    assert len(responses.calls) == 1

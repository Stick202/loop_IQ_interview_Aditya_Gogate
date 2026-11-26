import httpx
import pytest

from pipeline.client import ApiError, ContractError, OpenMeteoClient, check_contract


def client_for(responses, attempts=3):
    calls, sleeps = [], []

    def handler(request):
        calls.append(request)
        r = responses[min(len(calls), len(responses)) - 1]
        if isinstance(r, Exception):
            raise r
        return r

    c = OpenMeteoClient("https://example.test", max_attempts=attempts,
                        transport=httpx.MockTransport(handler), sleep=sleeps.append)
    return c, calls, sleeps


def test_retries_then_succeeds():
    c, calls, sleeps = client_for([httpx.Response(503), httpx.ConnectTimeout("slow"),
                                   httpx.Response(200, json={"ok": 1})])
    assert c.get({})[0] == {"ok": 1}
    assert len(calls) == 3
    assert sleeps[1] > sleeps[0]  # backoff grows


def test_honours_retry_after():
    c, _, sleeps = client_for([httpx.Response(429, headers={"Retry-After": "7"}),
                               httpx.Response(200, json={})])
    c.get({})
    assert sleeps == [7]


def test_truncated_body_is_retried():
    c, calls, _ = client_for([httpx.Response(200, text='{"a": '), httpx.Response(200, json={})])
    c.get({})
    assert len(calls) == 2


def test_bad_request_is_not_retried():
    c, calls, _ = client_for([httpx.Response(400, json={"error": True, "reason": "bad variable"})])
    with pytest.raises(ApiError, match="bad variable"):
        c.get({})
    assert len(calls) == 1


def test_gives_up():
    c, calls, _ = client_for([httpx.Response(500)])
    with pytest.raises(ApiError, match="gave up after 3"):
        c.get({})
    assert len(calls) == 3


def payload(**change):
    p = {"hourly_units": {"x": "m/s"}, "hourly": {"time": [0, 3600, 7200], "x": [1, 2, None]}}
    p["hourly"].update(change.get("hourly", {}))
    p["hourly_units"].update(change.get("units", {}))
    return p


def test_contract_accepts_partial_nulls():
    check_contract(payload(), "hourly", {"x": "m/s"})


@pytest.mark.parametrize("change, message", [
    ({"units": {"x": "undefined"}}, "undefined"),  # how the API reports an unknown variable
    ({"hourly": {"x": [None, None, None]}}, "entirely null"),
    ({"hourly": {"x": [1]}}, "1 values for 3"),
    ({"hourly": {"time": [0, 3600, 10800]}}, "one hour apart"),
    ({"hourly": {"time": [0, 0, 3600]}}, "strictly increasing"),
    ({"hourly": {"time": []}}, "no timestamps"),
])
def test_contract_rejects(change, message):
    with pytest.raises(ContractError, match=message):
        check_contract(payload(**change), "hourly", {"x": "m/s"})


def test_contract_rejects_missing_variable():
    with pytest.raises(ContractError, match="missing"):
        check_contract(payload(), "hourly", {"y": "m/s"})

"""Open-Meteo HTTP client: retries, plus a contract check on each response."""
from __future__ import annotations

import logging
import random
import time
from typing import Callable

import httpx

log = logging.getLogger(__name__)
RETRYABLE = {429, 500, 502, 503, 504}


class ApiError(RuntimeError):
    """The request failed, or retries ran out."""


class ContractError(RuntimeError):
    """The API answered 200 but the payload is not what the pipeline expects."""


class OpenMeteoClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 30,
        max_attempts: int = 5,
        backoff_seconds: float = 1.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.base_url = base_url
        self.max_attempts = max_attempts
        self.backoff = backoff_seconds
        self.sleep = sleep
        self.http = httpx.Client(
            timeout=timeout_seconds,
            transport=transport,
            headers={"User-Agent": "open-meteo-medallion-pipeline/1.0"},
        )

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.http.close()

    def get(self, params: dict) -> tuple[dict, str, int]:
        """Return (payload, final URL, HTTP status)."""
        reason = ""
        for attempt in range(1, self.max_attempts + 1):
            retry_after = None
            try:
                r = self.http.get(self.base_url, params=params)
                if r.status_code == 200:
                    return r.json(), str(r.url), r.status_code
                reason = f"HTTP {r.status_code}: {_reason(r)}"
                if r.status_code not in RETRYABLE:
                    raise ApiError(reason)  # a bad request will not fix itself
                retry_after = _seconds(r.headers.get("Retry-After"))
            except (httpx.TransportError, ValueError) as e:
                # ValueError: a truncated body that is not valid JSON
                reason = f"{type(e).__name__}: {e}"
            if attempt < self.max_attempts:
                wait = retry_after
                if wait is None:
                    wait = self.backoff * 2 ** (attempt - 1) * random.uniform(1, 1.25)
                log.warning("attempt %d/%d failed (%s), retrying in %.1fs",
                            attempt, self.max_attempts, reason, wait)
                self.sleep(wait)
        raise ApiError(f"gave up after {self.max_attempts} attempts: {reason}")


def _reason(r: httpx.Response) -> str:
    try:
        return r.json().get("reason", r.text[:200])
    except (ValueError, AttributeError):
        return r.text[:200]


def _seconds(value: str | None) -> float | None:
    try:
        return min(max(float(value), 0), 60) if value else None
    except ValueError:
        return None  # HTTP-date form: fall back to exponential backoff


def check_contract(payload: dict, block: str, expected_units: dict[str, str]) -> None:
    """Fail loudly on schema drift that the API reports with HTTP 200."""
    if not isinstance(payload, dict) or block not in payload:
        raise ContractError(f"response has no '{block}' block")
    data, units = payload[block], payload.get(f"{block}_units", {})
    times = data.get("time") or []
    if not times:
        raise ContractError(f"'{block}' has no timestamps")
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ContractError(f"'{block}' timestamps are not strictly increasing")
    if block == "hourly" and any(b - a != 3600 for a, b in zip(times, times[1:])):
        raise ContractError("hourly timestamps are not spaced one hour apart")
    for var, unit in expected_units.items():
        values = data.get(var)
        if values is None:
            raise ContractError(f"{block}.{var} is missing")
        if units.get(var) != unit:
            raise ContractError(f"{block}.{var}: unit {units.get(var)!r}, expected {unit!r}")
        if len(values) != len(times):
            raise ContractError(f"{block}.{var}: {len(values)} values for {len(times)} timestamps")
        if all(v is None for v in values):
            raise ContractError(f"{block}.{var} is entirely null")

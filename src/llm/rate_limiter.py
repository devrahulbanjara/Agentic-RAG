"""Client-side quota governor for the Gemini free tier.

The SDK never tells us how much quota is left, so we count usage ourselves rather
than guess with a fixed sleep. Three free-tier limits apply, all per project:
15 requests/min and 250k tokens/min (rolling 60s windows), and 1,000 requests/day
(resets at midnight Pacific).
"""

import json
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from loguru import logger

from src.llm.base import LLMDailyQuotaError

_WINDOW_SECONDS = 60.0
# Wake a hair after the window edge so the oldest entry is provably expired, instead
# of spinning through wake-recheck-sleep on clock jitter.
_WINDOW_GRACE = 0.1
_MIN_SLEEP = 0.1
# Google's daily quota rolls over on the Pacific calendar day, not UTC or local.
_QUOTA_TIMEZONE = ZoneInfo("America/Los_Angeles")


class RollingWindowLimiter:
    """Holds requests under the per-minute request and token caps."""

    def __init__(self, max_rpm: int, max_tpm: int) -> None:
        self._max_rpm = max_rpm
        self._max_tpm = max_tpm
        self._request_times: list[float] = []
        self._token_usage: list[tuple[float, int]] = []

    def _evict_expired(self, now: float) -> None:
        horizon = now - _WINDOW_SECONDS
        self._request_times = [t for t in self._request_times if t > horizon]
        self._token_usage = [(t, n) for t, n in self._token_usage if t > horizon]

    def reserve(self, estimated_tokens: int) -> None:
        # Wait until this request fits both caps, then claim its slot. We budget on
        # an estimate up front; record() trues it up once the real usage is known.
        while True:
            now = time.monotonic()
            self._evict_expired(now)

            used_requests = len(self._request_times)
            used_tokens = sum(n for _, n in self._token_usage)
            would_exceed_requests = used_requests >= self._max_rpm
            would_exceed_tokens = used_tokens + estimated_tokens > self._max_tpm

            if not (would_exceed_requests or would_exceed_tokens):
                self._request_times.append(now)
                return

            # Sleep only until the oldest in-window entry ages out and frees room.
            oldest = min(
                [t for t in self._request_times]
                + [t for t, _ in self._token_usage]
                + [now]
            )
            sleep_for = max(
                _MIN_SLEEP, _WINDOW_SECONDS + _WINDOW_GRACE - (now - oldest)
            )
            logger.info(
                "    Quota throttle: {}/{} RPM, {}/{} TPM (+{} est) — sleeping {:.1f}s",
                used_requests,
                self._max_rpm,
                used_tokens,
                self._max_tpm,
                estimated_tokens,
                sleep_for,
            )
            time.sleep(sleep_for)

    def record(self, actual_tokens: int) -> None:
        # Replace the estimate with real usage so the token window self-corrects.
        self._token_usage.append((time.monotonic(), actual_tokens))


class DailyQuotaLedger:
    """Tracks the per-day request cap, persisted so it survives restarts."""

    def __init__(self, max_rpd: int, state_path: Path) -> None:
        self._max_rpd = max_rpd
        self._state_path = state_path

    def _today(self) -> str:
        return datetime.now(_QUOTA_TIMEZONE).date().isoformat()

    def _load_count(self, today: str) -> int:
        # A missing or corrupt ledger just means "fresh day" — never a hard failure.
        # Worst case we under-count once, which the rolling limiter and the live 429
        # fallback still backstop.
        try:
            state = json.loads(self._state_path.read_text())
        except FileNotFoundError, ValueError:
            return 0
        if state.get("pt_date") != today:
            return 0
        return int(state.get("request_count", 0))

    def register_request(self) -> None:
        # Spend one request from today's budget, or refuse once it's gone.
        today = self._today()
        count = self._load_count(today)
        if count >= self._max_rpd:
            raise LLMDailyQuotaError(
                f"Daily Gemini quota reached ({count}/{self._max_rpd} requests); "
                "resets at midnight Pacific."
            )
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(
            json.dumps({"pt_date": today, "request_count": count + 1})
        )


class FreeTierRateLimiter:
    """The single gate the provider passes through on every model request."""

    def __init__(
        self,
        max_rpm: int,
        max_tpm: int,
        max_rpd: int,
        state_path: Path,
    ) -> None:
        self._window = RollingWindowLimiter(max_rpm, max_tpm)
        self._ledger = DailyQuotaLedger(max_rpd, state_path)

    def acquire(self, estimated_tokens: int) -> None:
        # Check the daily budget first — it's cheap and may abort before we ever wait
        # out the slower per-minute windows.
        self._ledger.register_request()
        self._window.reserve(estimated_tokens)

    def record(self, actual_tokens: int) -> None:
        self._window.record(actual_tokens)

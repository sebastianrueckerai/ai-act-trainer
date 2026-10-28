import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal

import httpx
import openai
from pydantic import BaseModel, ConfigDict, field_validator

CACHE_SECONDS = 30.0
BUDGET_MARKERS = ("ExceededBudget", "ExceededTokenBudget")
# The proxy refuses a call whose estimated cost would cross the budget, so a key with less
# than one heavy turn's cost left (about 0.005 USD) is spent as far as the student is concerned.
BUDGET_MARGIN_USD = 0.01


class Spend(BaseModel):
    spend: float = 0.0
    max_budget: float | None = None
    budget_reset_at: datetime | None = None

    @field_validator("budget_reset_at")
    @classmethod
    def naive_is_utc(cls, value: datetime | None) -> datetime | None:
        # The proxy keeps its reset times in UTC and may print them without an offset.
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    @property
    def exhausted(self) -> bool:
        return self.max_budget is not None and self.spend + BUDGET_MARGIN_USD >= self.max_budget


class BudgetState(BaseModel):
    model_config = ConfigDict(frozen=True)

    state: Literal["ok", "exhausted"] = "ok"
    scope: Literal["day", "month", "pool_day", "pool_month", "global", "seats"] | None = None
    resets_at: datetime | None = None


GLOBAL = BudgetState(state="exhausted", scope="global")
SEATS = BudgetState(state="exhausted", scope="seats")


class ProxyClient:
    """LiteLLM's admin API: users and keys with a budget, and what they have spent."""

    def __init__(
        self,
        base_url: str,
        admin_key: str,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.http = httpx.Client(
            base_url=base_url.rstrip("/").removesuffix("/v1"),
            headers={"Authorization": f"Bearer {admin_key}"},
            timeout=10.0,
            transport=transport,
        )
        self.clock = clock
        self.cache: dict[tuple[str, str], tuple[float, Spend]] = {}

    def close(self) -> None:
        self.http.close()

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        response = self.http.post(path, json=body)
        response.raise_for_status()
        return response.json()

    def new_user(self, user_id: str, max_budget: float, budget_duration: str = "1mo") -> None:
        self._post(
            "/user/new",
            {
                "user_id": user_id,
                "max_budget": max_budget,
                "budget_duration": budget_duration,
                # Otherwise the proxy hands out a key without a day budget alongside.
                "auto_create_key": False,
            },
        )

    def generate_key(
        self, user_id: str, max_budget: float, budget_duration: str = "1d", *, key_alias: str
    ) -> str:
        body = {
            "user_id": user_id,
            "max_budget": max_budget,
            "budget_duration": budget_duration,
            "key_alias": key_alias,
        }
        return self._post("/key/generate", body)["key"]

    def delete_key(self, key: str) -> None:
        self._post("/key/delete", {"keys": [key]})
        self.cache.pop(("key", key), None)

    def key_info(self, key: str, fresh: bool = False) -> Spend:
        return self._read("/key/info", "key", key, "info", fresh)

    def user_info(self, user_id: str, fresh: bool = False) -> Spend:
        return self._read("/user/info", "user_id", user_id, "user_info", fresh)

    def _read(self, path: str, param: str, value: str, field: str, fresh: bool) -> Spend:
        now = self.clock()
        cached = self.cache.get((param, value))
        if cached is not None and not fresh and now - cached[0] < CACHE_SECONDS:
            return cached[1]
        response = self.http.get(path, params={param: value})
        response.raise_for_status()
        spend = Spend.model_validate(response.json()[field])
        self.cache[(param, value)] = (now, spend)
        return spend


def caller_state(
    proxy: ProxyClient, key: str, user_id: str, guest: bool, fresh: bool = False
) -> BudgetState:
    """The month first: it holds longer than the day it contains."""
    month = proxy.user_info(user_id, fresh)
    if month.exhausted:
        scope = "pool_month" if guest else "month"
        return BudgetState(state="exhausted", scope=scope, resets_at=month.budget_reset_at)
    day = proxy.key_info(key, fresh)
    if day.exhausted:
        scope = "pool_day" if guest else "day"
        return BudgetState(state="exhausted", scope=scope, resets_at=day.budget_reset_at)
    return BudgetState()


def is_budget_error(error: BaseException | None) -> bool:
    """A proxy budget refusal anywhere in the chain of causes."""
    while error is not None:
        if isinstance(error, openai.APIError) and (
            error.type == "budget_exceeded" or any(m in str(error) for m in BUDGET_MARKERS)
        ):
            return True
        error = error.__cause__ or error.__context__
    return False

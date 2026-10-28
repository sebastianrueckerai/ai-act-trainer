import json
import time
from collections.abc import Callable
from typing import Any

import httpx

from app.llm.budget import ProxyClient

ADMIN_KEY = "sk-admin-test"
BASE_URL = "http://proxy:4000/v1"


class FakeProxy:
    """LiteLLM's admin API in memory: users and keys, each with a budget, a spend and a
    reset time. A test sets `spend` and `budget_reset_at` on an entry to move the clock."""

    def __init__(self) -> None:
        self.users: dict[str, dict[str, Any]] = {}
        self.keys: dict[str, dict[str, Any]] = {}
        self.requests: list[httpx.Request] = []

    def add(self, user_id: str, day: float, month: float) -> str:
        """A user with a month budget and one key under it with a day budget, as the
        account tool makes them. The key is named after the user."""
        self.users[user_id] = _entry(month, "1mo")
        key = f"sk-{user_id}"
        self.keys[key] = _entry(day, "1d") | {"user_id": user_id, "key_alias": user_id}
        return key

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.headers.get("authorization") != f"Bearer {ADMIN_KEY}":
            return httpx.Response(401, json={"error": {"message": "not the admin key"}})
        body = json.loads(request.content) if request.content else {}
        route = (request.method, request.url.path)
        if route == ("POST", "/user/new"):
            self.users[body["user_id"]] = _entry(body["max_budget"], body["budget_duration"])
            return httpx.Response(200, json={"user_id": body["user_id"], "key": None})
        if route == ("POST", "/key/generate"):
            key = f"sk-{body['key_alias']}"
            self.keys[key] = _entry(body["max_budget"], body["budget_duration"]) | {
                "user_id": body["user_id"],
                "key_alias": body["key_alias"],
            }
            return httpx.Response(200, json={"key": key, "user_id": body["user_id"]})
        if route == ("POST", "/key/delete"):
            for key in body["keys"]:
                del self.keys[key]
            return httpx.Response(200, json={"deleted_keys": body["keys"]})
        if route == ("GET", "/key/info"):
            key = request.url.params["key"]
            if key not in self.keys:
                return httpx.Response(404, json={"detail": {"error": "key not found"}})
            return httpx.Response(200, json={"key": key, "info": self.keys[key]})
        if route == ("GET", "/user/info"):
            user_id = request.url.params["user_id"]
            if user_id not in self.users:
                return httpx.Response(404, json={"detail": {"error": "user not found"}})
            return httpx.Response(200, json={"user_id": user_id, "user_info": self.users[user_id]})
        return httpx.Response(404, json={"detail": "no such route"})

    def client(self, clock: Callable[[], float] = time.monotonic) -> ProxyClient:
        return ProxyClient(
            BASE_URL, ADMIN_KEY, transport=httpx.MockTransport(self.handle), clock=clock
        )


def _entry(max_budget: float, budget_duration: str) -> dict[str, Any]:
    return {
        "spend": 0.0,
        "max_budget": max_budget,
        "budget_duration": budget_duration,
        "budget_reset_at": None,
    }

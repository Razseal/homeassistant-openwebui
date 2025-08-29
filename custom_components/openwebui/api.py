from __future__ import annotations
import aiohttp
from typing import Any, List

class OpenWebUIClient:
    def __init__(self, base_url: str, api_key: str, session: aiohttp.ClientSession):
        self._base = base_url.rstrip("/")
        self._session = session
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def chat_completions(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base}/api/chat/completions"
        async with self._session.post(url, headers=self._headers, json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def upload_file_bytes(self, name: str, data: bytes) -> dict[str, Any]:
        url = f"{self._base}/api/v1/files/"
        headers = {"Authorization": self._headers["Authorization"]}
        form = aiohttp.FormData()
        form.add_field("file", data, filename=name)
        async with self._session.post(url, headers=headers, data=form) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def list_models(self) -> list[str]:
        """Return a list of model IDs. Used for auth + model pick."""
        # Try OpenAI-compatible path first
        for path in ("/v1/models", "/api/models"):
            url = f"{self._base}{path}"
            try:
                async with self._session.get(url, headers={"Authorization": self._headers["Authorization"]}) as r:
                    if r.status == 401:
                        raise PermissionError("unauthorized")
                    r.raise_for_status()
                    data = await r.json()
            except Exception:
                continue

            # Normalize a few known shapes
            # OpenAI: {"data":[{"id":"gpt-4o-mini",...},...]}
            # OWUI (varies): {"data":[{"id":"llama3.1"},...]} or {"models":[{"id":"..."},...]}
            items = []
            if isinstance(data, dict):
                if isinstance(data.get("data"), list):
                    items = data["data"]
                elif isinstance(data.get("models"), list):
                    items = data["models"]
            if not items and isinstance(data, list):
                items = data

            model_ids: List[str] = []
            for it in items:
                if isinstance(it, dict):
                    mid = it.get("id") or it.get("name") or it.get("model")
                    if mid:
                        model_ids.append(str(mid))
                elif isinstance(it, str):
                    model_ids.append(it)

            if model_ids:
                return sorted(set(model_ids))

        # If we get here, both endpoints failed or returned empty.
        raise RuntimeError("Could not list models (auth or endpoint issue).")

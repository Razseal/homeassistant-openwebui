from __future__ import annotations
import aiohttp
from typing import Any

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

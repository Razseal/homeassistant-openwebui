from __future__ import annotations
import json
from typing import Any, List

from homeassistant.components.ai_task import (
    AITaskEntity,
    AITaskEntityFeature,
    GenDataTask,
    GenDataTaskResult,
)
from homeassistant.components.conversation import ChatLog
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_MODEL, CONF_DEFAULT_COLLECTIONS, DEFAULT_MODEL
from .api import OpenWebUIClient

JSON_INSTRUCTIONS = (
    "You are an API. When the user requests a structure, return ONLY valid JSON matching it. "
    "No prose and no code fences."
)

class OpenWebUIAITaskEntity(AITaskEntity):
    _attr_has_entity_name = True
    _attr_name = "OpenWebUI Task"
    _attr_supported_features = AITaskEntityFeature.GENERATE_DATA

    def __init__(self, hass: HomeAssistant, client: OpenWebUIClient, cfg: dict):
        self.hass = hass
        self._client = client
        self._model = cfg.get(CONF_MODEL, DEFAULT_MODEL)
        self._collections = [
            c.strip() for c in cfg.get(CONF_DEFAULT_COLLECTIONS, "").split(",") if c.strip()
        ]

    async def _async_generate_data(self, task: GenDataTask, chat_log: ChatLog) -> GenDataTaskResult:
        messages: List[dict[str, Any]] = [{"role": "system", "content": JSON_INSTRUCTIONS}]

        for item in chat_log.async_items():
            if item.is_user:
                messages.append({"role": "user", "content": item.content})
            elif item.is_assistant:
                messages.append({"role": "assistant", "content": item.content})

        messages.append({"role": "user", "content": task.instructions})

        payload: dict[str, Any] = {"model": self._model, "messages": messages}
        if self._collections:
            payload["files"] = [{"type": "collection", "id": cid} for cid in self._collections]

        data = await self._client.chat_completions(payload)
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")

        if not task.structure:
            return GenDataTaskResult(conversation_id=chat_log.conversation_id, data=text)

        try:
            parsed = json.loads(text)
        except Exception:
            parsed = {"_raw": text, "_error": "model did not return valid JSON"}

        return GenDataTaskResult(conversation_id=chat_log.conversation_id, data=parsed)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    client: OpenWebUIClient = hass.data[DOMAIN][entry.entry_id]["client"]
    cfg = hass.data[DOMAIN][entry.entry_id]["config"]
    async_add_entities([OpenWebUIAITaskEntity(hass, client, cfg)])

from __future__ import annotations
from typing import Any
import logging

from homeassistant.components import conversation as conv
from homeassistant.components.conversation import (
    ConversationEntity,
    ConversationInput,
)
from homeassistant.components.conversation.agent import ConversationResult
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import intent

from .const import (
    DOMAIN,
    CONF_MODEL,
    CONF_DEFAULT_COLLECTIONS,
    CONF_ALLOW_CONTROL,
    DEFAULT_MODEL,
)
from .api import OpenWebUIClient

_LOGGER = logging.getLogger(__name__)


class OpenWebUIConversationEntity(ConversationEntity):
    """Minimal, robust conversation agent for OpenWebUI."""
    _attr_has_entity_name = True
    _attr_name = "OpenWebUI"

    def __init__(self, hass: HomeAssistant, client: OpenWebUIClient, cfg: dict[str, Any]):
        self.hass = hass
        self._client = client
        self._model = cfg.get(CONF_MODEL, DEFAULT_MODEL)
        self._collections = [
            c.strip() for c in cfg.get(CONF_DEFAULT_COLLECTIONS, "").split(",") if c.strip()
        ]
        self._allow_control = bool(cfg.get(CONF_ALLOW_CONTROL, False))

    @property
    def supported_languages(self) -> str:
        return "*"

    @property
    def supported_features(self) -> conv.ConversationEntityFeature:
        return conv.ConversationEntityFeature.CONTROL if self._allow_control else 0

    async def _async_handle_message(
        self, user_input: ConversationInput, _chat_log
    ) -> ConversationResult:
        # Keep it simple: just send the current user text to OpenWebUI
        messages = [{"role": "user", "content": user_input.text}]

        payload: dict[str, Any] = {"model": self._model, "messages": messages}
        if self._collections:
            payload["files"] = [{"type": "collection", "id": cid} for cid in self._collections]

        data = await self._client.chat_completions(payload)
        content = (
            (data.get("choices") or [{}])[0]
            .get("message", {})
            .get("content", "")
            or "I don't have a response."
        )

        resp = intent.IntentResponse(language=user_input.language)
        resp.async_set_speech(content)

        return ConversationResult(
            conversation_id=getattr(_chat_log, "conversation_id", None),
            response=resp,
            continue_conversation=False,
        )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    client: OpenWebUIClient = hass.data[DOMAIN][entry.entry_id]["client"]
    cfg = hass.data[DOMAIN][entry.entry_id]["config"]
    async_add_entities([OpenWebUIConversationEntity(hass, client, cfg)])

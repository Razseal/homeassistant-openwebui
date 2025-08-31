from __future__ import annotations

from typing import Any, Mapping
from types import MappingProxyType

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client

from .const import (
    DOMAIN,
    ENTRY_TYPE,
    ENTRY_CONVERSATION,
    ENTRY_AI_TASK,
    CONF_BASE_URL,
    CONF_API_KEY,
    CONF_MODEL,
    CONF_DEFAULT_COLLECTIONS,
    CONF_ALLOW_CONTROL,
    DEFAULT_MODEL,
)
from .api import OpenWebUIClient


# --- USER STEP ---

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BASE_URL): str,
        vol.Required(CONF_API_KEY): str,
        vol.Required(ENTRY_TYPE, default=ENTRY_CONVERSATION): vol.In(
            [ENTRY_CONVERSATION, ENTRY_AI_TASK]
        ),
    }
)

# Options we’ll seed on first create (similar to RECOMMENDED_* pattern upstream)
RECOMMENDED_OPTIONS: dict[str, Any] = {
    CONF_MODEL: DEFAULT_MODEL,
    CONF_DEFAULT_COLLECTIONS: "",
    CONF_ALLOW_CONTROL: False,
}


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> list[str]:
    """Validate connectivity/auth and return available model ids."""
    session = aiohttp_client.async_get_clientsession(hass)
    client = OpenWebUIClient(data[CONF_BASE_URL].rstrip("/"), data[CONF_API_KEY], session)
    models = await client.list_models()
    if not models:
        raise RuntimeError("No models available")
    return models


class OpenWebUIConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for OpenWebUI Conversation/AI Task."""

    VERSION = 1

    # We’ll keep model list here only during create flow
    _models: list[str] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step, mirroring the OpenAI flow style."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA)

        errors: dict[str, str] = {}

        # Normalize
        user_input[CONF_BASE_URL] = user_input[CONF_BASE_URL].strip().rstrip("/")
        user_input[CONF_API_KEY] = user_input[CONF_API_KEY].strip()

        try:
            self._models = await validate_input(self.hass, user_input)
        except Exception as err:
            msg = str(err).lower()
            if "unauthorized" in msg or "401" in msg or "auth" in msg:
                errors["base"] = "invalid_auth"
            else:
                errors["base"] = "cannot_connect"
        else:
            # Create a stable unique_id so duplicates are blocked
            uid = f"{DOMAIN}:{user_input[ENTRY_TYPE]}:{user_input[CONF_BASE_URL]}"
            await self.async_set_unique_id(uid)
            self._abort_if_unique_id_configured()

            # We keep immutable conn bits in data; mutable bits in options
            data = {
                ENTRY_TYPE: user_input[ENTRY_TYPE],
                CONF_BASE_URL: user_input[CONF_BASE_URL],
                CONF_API_KEY: user_input[CONF_API_KEY],
            }

            # Seed options with recommended defaults, but if our DEFAULT_MODEL is available, use it
            options = dict(RECOMMENDED_OPTIONS)
            if self._models and DEFAULT_MODEL not in self._models:
                # fall back to first returned model
                options[CONF_MODEL] = self._models[0]

            title = "OpenWebUI Conversation" if user_input[ENTRY_TYPE] == ENTRY_CONVERSATION else "OpenWebUI AI Task"
            return self.async_create_entry(title=title, data=data, options=options)

        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors)

    # --- REAUTH (same spirit as upstream) ---

    async def async_step_reauth(self, data: dict[str, Any] | None = None) -> FlowResult:
        """Start re-auth; HA provides entry_id in context."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Confirm and update credentials."""
        entry = None
        if entry_id := self.context.get("entry_id"):
            entry = self.hass.config_entries.async_get_entry(entry_id)

        base_default = entry.data.get(CONF_BASE_URL, "") if entry else ""
        key_default = entry.data.get(CONF_API_KEY, "") if entry else ""

        schema = vol.Schema(
            {
                vol.Required(CONF_BASE_URL, default=base_default): str,
                vol.Required(CONF_API_KEY, default=key_default): str,
            }
        )

        errors: dict[str, str] = {}
        if user_input is not None and entry is not None:
            # Normalize
            user_input[CONF_BASE_URL] = user_input[CONF_BASE_URL].strip().rstrip("/")
            user_input[CONF_API_KEY] = user_input[CONF_API_KEY].strip()

            try:
                await validate_input(self.hass, user_input)
            except Exception as err:
                msg = str(err).lower()
                if "unauthorized" in msg or "401" in msg or "auth" in msg:
                    errors["base"] = "invalid_auth"
                else:
                    errors["base"] = "cannot_connect"
            else:
                new_data = {
                    **entry.data,
                    CONF_BASE_URL: user_input[CONF_BASE_URL],
                    CONF_API_KEY: user_input[CONF_API_KEY],
                }
                self.hass.config_entries.async_update_entry(entry, data=new_data)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(step_id="reauth_confirm", data_schema=schema, errors=errors)

    # --- Options flow hook ---

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return OpenWebUIOptionsFlow(config_entry)


class OpenWebUIOptionsFlow(OptionsFlow):
    """Options flow, modeled after the OpenAI pattern (but trimmed for OpenWebUI)."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage options."""
        options: dict[str, Any] | Mapping[str, Any] | MappingProxyType[str, Any] = self._config_entry.options

        # Pull current values with sensible defaults
        current_model = options.get(CONF_MODEL, DEFAULT_MODEL)
        current_collections = options.get(CONF_DEFAULT_COLLECTIONS, "")
        current_control = bool(options.get(CONF_ALLOW_CONTROL, False))

        # Try to refresh model list live (best effort)
        session = aiohttp_client.async_get_clientsession(self.hass)
        client = OpenWebUIClient(self._config_entry.data[CONF_BASE_URL], self._config_entry.data[CONF_API_KEY], session)
        try:
            models = await client.list_models()
            if current_model not in models:
                current_model = models[0]
        except Exception:
            models = [current_model]

        schema = vol.Schema(
            {
                vol.Required(CONF_MODEL, default=current_model): vol.In(models),
                vol.Optional(CONF_DEFAULT_COLLECTIONS, default=current_collections): str,
                vol.Optional(CONF_ALLOW_CONTROL, default=current_control): bool,
            }
        )

        if user_input is not None:
            # Normalize
            user_input[CONF_DEFAULT_COLLECTIONS] = user_input.get(CONF_DEFAULT_COLLECTIONS, "").strip()

            # Validate selected model is in the list we presented; if not, keep current
            if user_input.get(CONF_MODEL) not in models:
                user_input[CONF_MODEL] = current_model

            return self.async_create_entry(
                title="",
                data={
                    CONF_MODEL: user_input[CONF_MODEL],
                    CONF_DEFAULT_COLLECTIONS: user_input[CONF_DEFAULT_COLLECTIONS],
                    CONF_ALLOW_CONTROL: bool(user_input.get(CONF_ALLOW_CONTROL, False)),
                },
            )

        return self.async_show_form(step_id="init", data_schema=schema)

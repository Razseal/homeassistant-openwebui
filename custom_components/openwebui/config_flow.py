from __future__ import annotations

import uuid
import voluptuous as vol
from typing import List

from homeassistant import config_entries
from homeassistant.core import callback
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

# ----- Schemas -----
STEP_PICK_SCHEMA = vol.Schema({
    vol.Required(ENTRY_TYPE, default=ENTRY_CONVERSATION): vol.In([ENTRY_CONVERSATION, ENTRY_AI_TASK]),
})

STEP_CONNECT_SCHEMA = vol.Schema({
    vol.Required(CONF_BASE_URL, default="http://openwebui:8080"): str,
    vol.Required(CONF_API_KEY): str,
})


class OpenWebUIConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for OpenWebUI."""
    VERSION = 1

    def __init__(self) -> None:
        # create flow state
        self._entry_type: str | None = None
        self._base_url: str | None = None
        self._api_key: str | None = None
        self._models: List[str] = []

        # reauth state
        self._reauth_entry_id: str | None = None

    # ---------- CREATE ----------
    async def async_step_user(self, user_input=None) -> FlowResult:
        """Step 1: choose service type (conversation vs ai_task)."""
        if user_input is not None:
            self._entry_type = user_input[ENTRY_TYPE]
            # Reserve a unique ID up front; avoids DB collisions.
            await self.async_set_unique_id(f"{DOMAIN}_{uuid.uuid4()}")
            self._abort_if_unique_id_configured()
            return await self.async_step_connect()

        return self.async_show_form(step_id="user", data_schema=STEP_PICK_SCHEMA)

    async def async_step_connect(self, user_input=None) -> FlowResult:
        """Step 2: base URL + API key; validate by listing models."""
        errors: dict[str, str] = {}

        if user_input is not None:
            base_url = user_input[CONF_BASE_URL].strip()
            api_key = user_input[CONF_API_KEY].strip()

            session = aiohttp_client.async_get_clientsession(self.hass)
            client = OpenWebUIClient(base_url, api_key, session)

            try:
                models = await client.list_models()
                if not models:
                    errors["base"] = "cannot_connect"
                else:
                    self._base_url = base_url
                    self._api_key = api_key
                    self._models = models
                    return await self.async_step_model()
            except PermissionError:
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "cannot_connect"

        return self.async_show_form(step_id="connect", data_schema=STEP_CONNECT_SCHEMA, errors=errors)

    async def async_step_model(self, user_input=None) -> FlowResult:
        """Step 3: pick model + options."""
        assert self._entry_type and self._base_url and self._api_key and self._models

        default_model = DEFAULT_MODEL if DEFAULT_MODEL in self._models else self._models[0]

        schema = vol.Schema({
            vol.Required(CONF_MODEL, default=default_model): vol.In(self._models),
            vol.Optional(CONF_DEFAULT_COLLECTIONS, default=""): str,
            vol.Optional(CONF_ALLOW_CONTROL, default=False): bool,
        })

        if user_input is not None:
            # Keep immutable connection bits in data; mutable in options.
            data = {
                ENTRY_TYPE: self._entry_type,
                CONF_BASE_URL: self._base_url,
                CONF_API_KEY: self._api_key,
            }
            options = {
                CONF_MODEL: user_input[CONF_MODEL],
                CONF_DEFAULT_COLLECTIONS: user_input.get(CONF_DEFAULT_COLLECTIONS, "").strip(),
                CONF_ALLOW_CONTROL: user_input.get(CONF_ALLOW_CONTROL, False),
            }
            title = "OpenWebUI Conversation" if self._entry_type == ENTRY_CONVERSATION else "OpenWebUI AI Task"
            return self.async_create_entry(title=title, data=data, options=options)

        return self.async_show_form(step_id="model", data_schema=schema)

    # ---------- REAUTH ----------
    async def async_step_reauth(self, data) -> FlowResult:
        """Begin re-auth flow (trigger with ConfigEntryAuthFailed)."""
        # data may include 'entry_id' depending on caller
        self._reauth_entry_id = (data or {}).get("entry_id")
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}

        # pull current entry to prefill
        base_default = ""
        key_default = ""
        entry = None
        if self._reauth_entry_id:
            entry = self.hass.config_entries.async_get_entry(self._reauth_entry_id)
        if entry:
            base_default = entry.data.get(CONF_BASE_URL, "")
            key_default = entry.data.get(CONF_API_KEY, "")

        schema = vol.Schema({
            vol.Required(CONF_BASE_URL, default=base_default): str,
            vol.Required(CONF_API_KEY, default=key_default): str,
        })

        if user_input is not None:
            new_base = user_input[CONF_BASE_URL].strip()
            new_key = user_input[CONF_API_KEY].strip()

            session = aiohttp_client.async_get_clientsession(self.hass)
            client = OpenWebUIClient(new_base, new_key, session)

            try:
                models = await client.list_models()
                if not models:
                    errors["base"] = "cannot_connect"
                else:
                    if entry:
                        new_data = {**entry.data, CONF_BASE_URL: new_base, CONF_API_KEY: new_key}
                        self.hass.config_entries.async_update_entry(entry, data=new_data)
                        await self.hass.config_entries.async_reload(entry.entry_id)
                    return self.async_abort(reason="reauth_successful")
            except PermissionError:
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "cannot_connect"

        return self.async_show_form(step_id="reauth_confirm", data_schema=schema, errors=errors)

    # ---------- OPTIONS ----------
    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return OpenWebUIOptionsFlowHandler(config_entry)


class OpenWebUIOptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow: change model / collections / CONTROL. Reload is handled by update_listener."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry
        self._models: list[str] = []

    async def async_step_init(self, user_input=None) -> FlowResult:
        cfg = {**self._entry.data, **self._entry.options}

        # Try to refresh the model list live
        session = aiohttp_client.async_get_clientsession(self.hass)
        client = OpenWebUIClient(cfg[CONF_BASE_URL], cfg[CONF_API_KEY], session)
        try:
            self._models = await client.list_models()
        except Exception:
            # Fall back to current model only
            current = cfg.get(CONF_MODEL, DEFAULT_MODEL)
            self._models = [current]

        current_model = cfg.get(CONF_MODEL, DEFAULT_MODEL)
        if current_model not in self._models:
            current_model = self._models[0]

        schema = vol.Schema({
            vol.Required(CONF_MODEL, default=current_model): vol.In(self._models),
            vol.Optional(CONF_DEFAULT_COLLECTIONS, default=cfg.get(CONF_DEFAULT_COLLECTIONS, "")): str,
            vol.Optional(CONF_ALLOW_CONTROL, default=cfg.get(CONF_ALLOW_CONTROL, False)): bool,
        })

        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    CONF_MODEL: user_input[CONF_MODEL],
                    CONF_DEFAULT_COLLECTIONS: user_input.get(CONF_DEFAULT_COLLECTIONS, "").strip(),
                    CONF_ALLOW_CONTROL: user_input.get(CONF_ALLOW_CONTROL, False),
                },
            )

        return self.async_show_form(step_id="init", data_schema=schema)

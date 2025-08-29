from __future__ import annotations

import uuid
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant
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

STEP_PICK_SCHEMA = vol.Schema({
    vol.Required(ENTRY_TYPE, default=ENTRY_CONVERSATION): vol.In([ENTRY_CONVERSATION, ENTRY_AI_TASK]),
})

STEP_CONNECT_SCHEMA = vol.Schema({
    vol.Required(CONF_BASE_URL, default="http://openwebui:8080"): str,
    vol.Required(CONF_API_KEY): str,
})

class OpenWebUIConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    # State for create flow
    def __init__(self) -> None:
        self._entry_type: str | None = None
        self._base_url: str | None = None
        self._api_key: str | None = None
        self._models: list[str] = []

        # State for reauth
        self._reauth_entry_id: str | None = None

    # ---------- CREATE ----------
    async def async_step_user(self, user_input=None) -> FlowResult:
        """Step 1: pick Conversation vs AI Task."""
        if user_input is not None:
            self._entry_type = user_input[ENTRY_TYPE]
            # Reserve a unique ID up front so DB never collides
            await self.async_set_unique_id(f"{DOMAIN}_{uuid.uuid4()}")
            self._abort_if_unique_id_configured()
            return await self.async_step_connect()
        return self.async_show_form(step_id="user", data_schema=STEP_PICK_SCHEMA)

    async def async_step_connect(self, user_input=None) -> FlowResult:
        """Step 2: base URL + API key, validate by listing models."""
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
        """Step 3: model + options."""
        assert self._entry_type and self._base_url and self._api_key and self._models

        schema = vol.Schema({
            vol.Required(
                CONF_MODEL,
                default=(DEFAULT_MODEL if DEFAULT_MODEL in self._models else self._models[0]),
            ): vol.In(self._models),
            vol.Optional(CONF_DEFAULT_COLLECTIONS, default=""): str,
            vol.Optional(CONF_ALLOW_CONTROL, default=False): bool,
        })

        if user_input is not None:
            # Keep immutable bits in data, mutable bits in options
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
    async def async_step_reauth(self, entry_data) -> FlowResult:
        """Triggered when the integration requests reauth (e.g., 401)."""
        self._reauth_entry_id = entry_data["entry_id"]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None) -> FlowResult:
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
                    # Update the existing entry's data
                    entry = self.hass.config_entries.async_get_entry(self._reauth_entry_id)
                    if entry:
                        new_data = {**entry.data, CONF_BASE_URL: base_url, CONF_API_KEY: api_key}
                        self.hass.config_entries.async_update_entry(entry, data=new_data)
                        await self.hass.config_entries.async_reload(entry.entry_id)
                    return self.async_abort(reason="reauth_successful")
            except PermissionError:
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "cannot_connect"

        # Prefill with current
        base = ""
        key = ""
        if self._reauth_entry_id:
            entry = self.hass.config_entries.async_get_entry(self._reauth_entry_id)
            if entry:
                base = entry.data.get(CONF_BASE_URL, "")
                key = entry.data.get(CONF_API_KEY, "")

        schema = vol.Schema({
            vol.Required(CONF_BASE_URL, default=base): str,
            vol.Required(CONF_API_KEY, default=key): str,
        })
        return self.async_show_form(step_id="reauth_confirm", data_schema=schema, errors=errors)

    # ---------- OPTIONS ----------
    @staticmethod
    def _merged_cfg(hass: HomeAssistant, entry_id: str) -> dict:
        entry = hass.config_entries.async_get_entry(entry_id)
        cfg = {**(entry.data if entry else {}), **(entry.options if entry else {})}
        return cfg

    async def async_step_options(self) -> FlowResult:
        return OpenWebUIOptionsFlowHandler(self.hass, self._merged_cfg, self.hass).async_step_init(self)

class OpenWebUIOptionsFlowHandler(config_entries.OptionsFlow):
    """Options: change model / collections / CONTROL. Saving reloads the entry via update_listener."""
    def __init__(self, hass: HomeAssistant, cfg_getter, *_):
        self.hass = hass
        self._get = cfg_getter
        self._models: list[str] = []

    async def async_step_init(self, flow: OpenWebUIConfigFlow, user_input=None) -> FlowResult:
        entry = flow.config_entry
        cfg = self._get(self.hass, entry.entry_id)

        # Refresh model list live so dropdown is accurate
        session = aiohttp_client.async_get_clientsession(self.hass)
        client = OpenWebUIClient(cfg[CONF_BASE_URL], cfg[CONF_API_KEY], session)
        try:
            self._models = await client.list_models()
        except Exception:
            # Fall back to current model if model listing fails
            self._models = [cfg.get(CONF_MODEL, DEFAULT_MODEL)]

        schema = vol.Schema({
            vol.Required(
                CONF_MODEL,
                default=(cfg.get(CONF_MODEL, DEFAULT_MODEL) if cfg.get(CONF_MODEL) in self._models else (self._models[0] if self._models else DEFAULT_MODEL)),
            ): vol.In(self._models or [cfg.get(CONF_MODEL, DEFAULT_MODEL)]),
            vol.Optional(CONF_DEFAULT_COLLECTIONS, default=cfg.get(CONF_DEFAULT_COLLECTIONS, "")): str,
            vol.Optional(CONF_ALLOW_CONTROL, default=cfg.get(CONF_ALLOW_CONTROL, False)): bool,
        })

        if user_input is not None:
            # Options only; data (base_url, api_key) unchanged here
            return self.async_create_entry(
                title="",
                data={
                    CONF_MODEL: user_input[CONF_MODEL],
                    CONF_DEFAULT_COLLECTIONS: user_input.get(CONF_DEFAULT_COLLECTIONS, "").strip(),
                    CONF_ALLOW_CONTROL: user_input.get(CONF_ALLOW_CONTROL, False),
                },
            )

        return self.async_show_form(step_id="init", data_schema=schema)

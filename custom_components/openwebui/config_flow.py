from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client

from .const import (
    DOMAIN,
    CONF_BASE_URL,
    CONF_API_KEY,
    CONF_MODEL,
    CONF_DEFAULT_COLLECTIONS,
    CONF_ALLOW_CONTROL,
    DEFAULT_MODEL,
)
from .api import OpenWebUIClient

STEP_USER_SCHEMA = vol.Schema({
    vol.Required(CONF_BASE_URL, default="http://openwebui:8080"): str,
    vol.Required(CONF_API_KEY): str,
})

class OpenWebUIConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._base_url: str | None = None
        self._api_key: str | None = None
        self._models: list[str] = []

    async def async_step_user(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            base_url = user_input[CONF_BASE_URL].strip()
            api_key = user_input[CONF_API_KEY].strip()
            # Validate/auth here by listing models
            session = aiohttp_client.async_get_clientsession(self.hass)
            client = OpenWebUIClient(base_url, api_key, session)
            try:
                models = await client.list_models()
                if not models:
                    errors["base"] = "cannot_connect"
                else:
                    # success → store and proceed
                    self._base_url = base_url
                    self._api_key = api_key
                    self._models = models
                    return await self.async_step_model()
            except PermissionError:
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "cannot_connect"

        return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors)

    async def async_step_model(self, user_input=None) -> FlowResult:
        assert self._base_url and self._api_key and self._models

        schema = vol.Schema({
            vol.Required(CONF_MODEL, default=(DEFAULT_MODEL if DEFAULT_MODEL in self._models else self._models[0])): vol.In(self._models),
            vol.Optional(CONF_DEFAULT_COLLECTIONS, default=""): str,
            vol.Optional(CONF_ALLOW_CONTROL, default=False): bool,
        })

        if user_input is not None:
            data = {
                CONF_BASE_URL: self._base_url,
                CONF_API_KEY: self._api_key,
                CONF_MODEL: user_input[CONF_MODEL],
                CONF_DEFAULT_COLLECTIONS: user_input.get(CONF_DEFAULT_COLLECTIONS, "").strip(),
                CONF_ALLOW_CONTROL: user_input.get(CONF_ALLOW_CONTROL, False),
            }
            return self.async_create_entry(title="OpenWebUI", data=data)

        return self.async_show_form(step_id="model", data_schema=schema)

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_BASE_URL,
    CONF_API_KEY,
    CONF_MODEL,
    CONF_DEFAULT_COLLECTIONS,
    CONF_ALLOW_CONTROL,
    DEFAULT_MODEL,
)

class OpenWebUIConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        if user_input is not None:
            user_input[CONF_DEFAULT_COLLECTIONS] = user_input.get(CONF_DEFAULT_COLLECTIONS, "").strip()
            return self.async_create_entry(title="OpenWebUI", data=user_input)

        schema = vol.Schema({
            vol.Required(CONF_BASE_URL, default="http://openwebui:8080"): str,
            vol.Required(CONF_API_KEY): str,
            vol.Optional(CONF_MODEL, default=DEFAULT_MODEL): str,
            vol.Optional(CONF_DEFAULT_COLLECTIONS, default=""): str,
            vol.Optional(CONF_ALLOW_CONTROL, default=False): bool,
        })
        return self.async_show_form(step_id="user", data_schema=schema)

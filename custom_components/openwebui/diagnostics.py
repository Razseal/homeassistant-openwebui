from __future__ import annotations

from typing import Any, Dict, List, Optional

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client

from .const import (
    DOMAIN,
    ENTRY_TYPE,
    CONF_BASE_URL,
    CONF_API_KEY,
    CONF_MODEL,
    CONF_DEFAULT_COLLECTIONS,
    CONF_ALLOW_CONTROL,
)
from .api import OpenWebUIClient

REDACT_FIELDS = {CONF_API_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> Dict[str, Any]:
    """Return diagnostics for a config entry."""
    cfg = {**entry.data, **entry.options}
    redacted_cfg = async_redact_data(
        {
            "entry_type": cfg.get(ENTRY_TYPE),
            "base_url": cfg.get(CONF_BASE_URL),
            "model": cfg.get(CONF_MODEL),
            "default_collections": cfg.get(CONF_DEFAULT_COLLECTIONS),
            "allow_control": cfg.get(CONF_ALLOW_CONTROL, False),
            # keep api_key present so it can be redacted (shows "REDACTED" in output)
            "api_key": cfg.get(CONF_API_KEY),
        },
        REDACT_FIELDS,
    )

    # Live health check: try listing models
    session = aiohttp_client.async_get_clientsession(hass)
    client = OpenWebUIClient(cfg.get(CONF_BASE_URL, ""), cfg.get(CONF_API_KEY, ""), session)

    models: List[str] = []
    list_models_error: Optional[str] = None
    try:
        models = await client.list_models()
    except Exception as e:
        list_models_error = f"{type(e).__name__}: {e}"

    return {
        "config": redacted_cfg,
        "live_check": {
            "models": models,
            "list_models_error": list_models_error,
        },
        "hass_entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "state": entry.state.as_dict() if hasattr(entry.state, "as_dict") else str(entry.state),
            "unique_id": entry.unique_id,
        },
        "runtime": {
            # room for future: last error/timeouts if you store them in hass.data
        },
    }

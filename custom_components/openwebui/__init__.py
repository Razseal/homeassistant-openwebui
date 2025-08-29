from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client

from .const import DOMAIN, ENTRY_TYPE, ENTRY_CONVERSATION, ENTRY_AI_TASK
from .api import OpenWebUIClient

PLATFORM_FOR_TYPE = {
    ENTRY_CONVERSATION: ["conversation"],
    ENTRY_AI_TASK: ["ai_task"],
}

async def _update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    # Any options change triggers a reload of this entry
    await hass.config_entries.async_reload(entry.entry_id)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = aiohttp_client.async_get_clientsession(hass)

    # merge options (mutable) on top of data (immutable)
    cfg = {**entry.data, **entry.options}

    client = OpenWebUIClient(
        cfg["base_url"],
        cfg["api_key"],
        session,
    )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"client": client, "config": cfg}

    entry.async_on_unload(entry.add_update_listener(_update_listener))

    entry_type = cfg.get(ENTRY_TYPE, ENTRY_CONVERSATION)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORM_FOR_TYPE[entry_type])
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    cfg = {**entry.data, **entry.options}
    entry_type = cfg.get(ENTRY_TYPE, ENTRY_CONVERSATION)
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORM_FOR_TYPE[entry_type])
    if ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return ok

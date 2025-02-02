"""Calaos integration for Home Assistant."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import CalaosCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.COVER,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TEXT,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = CalaosCoordinator(hass, entry)
    try:
        await coordinator.connect()
    except Exception as ex:
        raise ConfigEntryNotReady(f"Config Not Ready: {ex}")

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await coordinator.declare_noentity_devices()

    #hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, coordinator.stop_poller)
    #entry.async_on_unload(coordinator.stop_poller)

    entry.async_create_task(
        hass, hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    )
    #entry.async_create_background_task(
    #    hass, coordinator.start_poller(), "Calaos poller"
    #)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok

import logging
from http.client import RemoteDisconnected
from urllib.error import URLError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_ID, CONF_TYPE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry
from homeassistant.helpers.event import async_track_time_interval

from pycalaos import Client
from pycalaos.item.common import Item

from .const import DOMAIN, EVENT_DOMAIN, POLL_INTERVAL
from .entity import CalaosEntity
from .no_entity import (
    translate_trigger as noentity_translate_trigger,
    triggers as noentity_triggers,
)

_LOGGER = logging.getLogger(__name__)


class CalaosCoordinator:

    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        self.hass = hass
        self.client = None
        self.entry_id = config_entry.entry_id
        self.calaos_url = config_entry.data["url"]
        self.calaos_username = config_entry.data["username"]
        self.calaos_password = config_entry.data["password"]
        self._entity_by_id = {}
        self._device_id_by_id = {}
        self.stopper = None
        self.client = None

    async def connect(self) -> None:
        _LOGGER.debug("Connecting to %s", self.calaos_url)
        self.client = Client(self.calaos_url, self.calaos_username, self.calaos_password)
        await self.client.init()
        await self.client.reload_home()

    async def declare_noentity_devices(self) -> None:
        dev_registry = device_registry.async_get(self.hass)
        dev_registry.async_get_or_create(
            config_entry_id=self.entry_id,
            identifiers={(DOMAIN, self.entry_id)},
            name="Calaos server",
            manufacturer="Calaos",
            model="Calaos v3",
        )

        for itemType in noentity_triggers.keys():
            for item in self.client.items_by_type(itemType):
                await self.declare_device(dev_registry, self.entry_id, item)

    async def declare_device(
        self, registry: device_registry.DeviceRegistry, entry_id: str, item: Item
    ) -> None:
        _LOGGER.debug("Declaring device without entity for %s", item.name)
        device = registry.async_get_or_create(
            config_entry_id=entry_id,
            identifiers={(DOMAIN, entry_id, item.id)},
            name=item.name,
            manufacturer="Calaos",
            model="Calaos v3",
            suggested_area=item.room.name,
            via_device=(DOMAIN, entry_id),
        )
        self._device_id_by_id[item.id] = device.id

    @callback
    def register(self, item_id: str, entity: CalaosEntity) -> None:
        self._entity_by_id[item_id] = entity

    def item(self, id: str) -> Item:
        return self.client.items[id]

    def items_by_gui_type(self, gui_type: str) -> list[Item]:
        return self.client.items_by_gui_type(gui_type)

    async def async_update(self) -> None:
        if not self.client:
            try:
                await self.connect()
            except Exception as ex:
                _LOGGER.error(f"unknown error before polling: {ex}")
                self.client = None
                return
        try:
            events = await self.client.wait()
        except (RemoteDisconnected, URLError) as ex:
            _LOGGER.error(f"connection error while polling: {ex}")
            self.client = None
            return
        except Exception as ex:
            _LOGGER.error(f"unknown error while polling: {ex}")
            self.client = None
            return
        if len(events) > 0:
            _LOGGER.debug(f"Calaos events: {events}")
            for evt in events:
                # If the item has an entity, simply schedule its update
                if evt.item.id in self._entity_by_id:
                    _LOGGER.debug(f"Event for known entity: {evt}")
                    entity = self._entity_by_id[evt.item.id]
                    entity.async_schedule_update_ha_state()
                    continue

                # Fire HA events for noentity items
                event_type = noentity_translate_trigger(evt)
                if event_type:
                    _LOGGER.debug(
                        f"Event for known no-entity device: {evt} -> {event_type}"
                    )
                    if evt.item.id in self._device_id_by_id:
                        self.hass.bus.async_fire(
                            EVENT_DOMAIN,
                            {
                                CONF_DEVICE_ID: self._device_id_by_id[evt.item.id],
                                CONF_TYPE: event_type,
                            },
                        )

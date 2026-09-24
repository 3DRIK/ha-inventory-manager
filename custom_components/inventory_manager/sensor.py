"""Sensor platform for Inventory Manager."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_EXPIRY_WARNING_DAYS,
    CONF_LOCATIONS,
    DEFAULT_EXPIRY_WARNING_DAYS,
    DOMAIN,
    SIGNAL_DATA_UPDATED,
    SIGNAL_LOCATIONS_UPDATED,
)
from .storage import InventoryManagerStore


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Inventory Manager",
        manufacturer="Custom",
        model="Inventory Manager",
        entry_type="service",
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    store: InventoryManagerStore = hass.data[DOMAIN][entry.entry_id]["store"]

    created_locations: set[str] = set()

    @callback
    def _add_location_sensors() -> None:
        new_entities: list[SensorEntity] = []
        for location in store.locations:
            if location in created_locations:
                continue
            created_locations.add(location)
            new_entities.append(InventoryLocationSensor(entry, store, location))
        if new_entities:
            async_add_entities(new_entities)

    _add_location_sensors()
    async_add_entities(
        [
            InventoryLowStockSensor(entry, store),
            InventoryExpiringSoonSensor(entry, store),
            InventoryExpiredSensor(entry, store),
            InventoryTotalItemsSensor(entry, store),
        ]
    )

    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            f"{SIGNAL_LOCATIONS_UPDATED}_{entry.entry_id}",
            _add_location_sensors,
        )
    )


class _BaseInventorySensor(SensorEntity):
    """Common refresh-on-signal behaviour."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, store: InventoryManagerStore) -> None:
        self._entry = entry
        self._store = store
        self._attr_device_info = _device_info(entry)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_DATA_UPDATED}_{self._entry.entry_id}",
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_schedule_update_ha_state(force_refresh=False)
        self.async_write_ha_state()


class InventoryLocationSensor(_BaseInventorySensor):
    """One sensor per inventory location, e.g. Špajza, Chladnička."""

    _attr_icon = "mdi:package-variant-closed"

    def __init__(
        self, entry: ConfigEntry, store: InventoryManagerStore, location: str
    ) -> None:
        super().__init__(entry, store)
        self._location = location
        self._attr_unique_id = f"{entry.entry_id}_location_{location}"
        self._attr_name = location
        self._attr_native_unit_of_measurement = "položiek"

    @property
    def native_value(self) -> int:
        return len(self._store.items_for_location(self._location))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        items = self._store.items_for_location(self._location)
        low_stock = self._store.low_stock_items(self._location)
        warning_days = self._entry.options.get(
            CONF_EXPIRY_WARNING_DAYS, DEFAULT_EXPIRY_WARNING_DAYS
        )
        expiring = self._store.expiring_items(warning_days, self._location)
        return {
            "location": self._location,
            "items": self._store.as_item_list(items),
            "low_stock_count": len(low_stock),
            "low_stock_items": [i["name"] for i in low_stock.values()],
            "expiring_soon_count": len(expiring),
            "expiring_soon_items": [i["name"] for i in expiring.values()],
        }


class InventoryLowStockSensor(_BaseInventorySensor):
    """Global count of items at/under their configured threshold."""

    _attr_icon = "mdi:alert-circle-outline"
    _attr_translation_key = "low_stock"

    def __init__(self, entry: ConfigEntry, store: InventoryManagerStore) -> None:
        super().__init__(entry, store)
        self._attr_unique_id = f"{entry.entry_id}_low_stock"
        self._attr_name = "Nízky stav zásob"
        self._attr_native_unit_of_measurement = "položiek"

    @property
    def native_value(self) -> int:
        return len(self._store.low_stock_items())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        low_stock = self._store.low_stock_items()
        return {"items": self._store.as_item_list(low_stock)}


class InventoryExpiringSoonSensor(_BaseInventorySensor):
    """Global count of items expiring within the configured window."""

    _attr_icon = "mdi:calendar-alert"

    def __init__(self, entry: ConfigEntry, store: InventoryManagerStore) -> None:
        super().__init__(entry, store)
        self._attr_unique_id = f"{entry.entry_id}_expiring_soon"
        self._attr_name = "Čoskoro exspiruje"
        self._attr_native_unit_of_measurement = "položiek"

    @property
    def native_value(self) -> int:
        warning_days = self._entry.options.get(
            CONF_EXPIRY_WARNING_DAYS, DEFAULT_EXPIRY_WARNING_DAYS
        )
        return len(self._store.expiring_items(warning_days))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        warning_days = self._entry.options.get(
            CONF_EXPIRY_WARNING_DAYS, DEFAULT_EXPIRY_WARNING_DAYS
        )
        expiring = self._store.expiring_items(warning_days)
        items = sorted(
            self._store.as_item_list(expiring), key=lambda i: i.get("expiration") or ""
        )
        return {"warning_days": warning_days, "items": items}


class InventoryExpiredSensor(_BaseInventorySensor):
    """Global count of items already past their expiration date."""

    _attr_icon = "mdi:calendar-remove"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry, store: InventoryManagerStore) -> None:
        super().__init__(entry, store)
        self._attr_unique_id = f"{entry.entry_id}_expired"
        self._attr_name = "Exspirované položky"
        self._attr_native_unit_of_measurement = "položiek"

    @property
    def native_value(self) -> int:
        return len(self._store.expired_items())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"items": self._store.as_item_list(self._store.expired_items())}


class InventoryTotalItemsSensor(_BaseInventorySensor):
    """Total number of distinct item entries across all locations."""

    _attr_icon = "mdi:archive-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry, store: InventoryManagerStore) -> None:
        super().__init__(entry, store)
        self._attr_unique_id = f"{entry.entry_id}_total_items"
        self._attr_name = "Celkový počet položiek"
        self._attr_native_unit_of_measurement = "položiek"

    @property
    def native_value(self) -> int:
        return len(self._store.items)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"locations": self._store.locations}

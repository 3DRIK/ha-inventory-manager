"""The Inventory Manager integration."""
from __future__ import annotations

import logging
from datetime import timedelta

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue, async_delete_issue

from .const import (
    ATTR_AMOUNT,
    ATTR_CATEGORY,
    ATTR_EXPIRATION,
    ATTR_ITEM_ID,
    ATTR_LOCATION,
    ATTR_NAME,
    ATTR_NOTES,
    ATTR_QUANTITY,
    ATTR_THRESHOLD,
    ATTR_UNIT,
    CARD_FILENAME,
    CARD_VERSION,
    CHECK_INTERVAL_MINUTES,
    CONF_EXPIRY_WARNING_DAYS,
    CONF_LOCATIONS,
    DEFAULT_EXPIRY_WARNING_DAYS,
    DOMAIN,
    EVENT_EXPIRING_SOON,
    EVENT_LOW_STOCK,
    PLATFORMS,
    SIGNAL_DATA_UPDATED,
    SIGNAL_LOCATIONS_UPDATED,
    STATIC_URL_BASE,
)
from .storage import InventoryManagerStore
from .websocket_api import async_register_websocket_commands

_LOGGER = logging.getLogger(__name__)

SERVICE_ADD_ITEM = "add_item"
SERVICE_UPDATE_ITEM = "update_item"
SERVICE_REMOVE_ITEM = "remove_item"
SERVICE_CONSUME = "consume"
SERVICE_RESTOCK = "restock"
SERVICE_ADD_LOCATION = "add_location"
SERVICE_REMOVE_LOCATION = "remove_location"

_ADD_ITEM_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_NAME): cv.string,
        vol.Required(ATTR_LOCATION): cv.string,
        vol.Optional(ATTR_QUANTITY, default=1): vol.Coerce(float),
        vol.Optional(ATTR_UNIT): cv.string,
        vol.Optional(ATTR_EXPIRATION): cv.string,
        vol.Optional(ATTR_THRESHOLD): vol.Coerce(float),
        vol.Optional(ATTR_CATEGORY): cv.string,
        vol.Optional(ATTR_NOTES): cv.string,
    }
)

_UPDATE_ITEM_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ITEM_ID): cv.string,
        vol.Optional(ATTR_NAME): cv.string,
        vol.Optional(ATTR_LOCATION): cv.string,
        vol.Optional(ATTR_QUANTITY): vol.Coerce(float),
        vol.Optional(ATTR_UNIT): cv.string,
        vol.Optional(ATTR_EXPIRATION): cv.string,
        vol.Optional(ATTR_THRESHOLD): vol.Coerce(float),
        vol.Optional(ATTR_CATEGORY): cv.string,
        vol.Optional(ATTR_NOTES): cv.string,
    }
)

_ITEM_ID_SCHEMA = vol.Schema({vol.Required(ATTR_ITEM_ID): cv.string})

_QUANTITY_CHANGE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ITEM_ID): cv.string,
        vol.Optional(ATTR_AMOUNT, default=1): vol.Coerce(float),
    }
)

_LOCATION_SCHEMA = vol.Schema({vol.Required(ATTR_NAME): cv.string})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    store = InventoryManagerStore(hass, entry.entry_id)
    await store.async_load(default_locations=entry.options.get(CONF_LOCATIONS))

    hass.data[DOMAIN][entry.entry_id] = {"store": store}

    # Register frontend card as a static resource + auto-inject it, so the
    # user does not need to add a Lovelace resource by hand.
    await _async_register_frontend(hass)

    # WS API + services are process-wide, only register once.
    if len(hass.data[DOMAIN]) == 1:
        async_register_websocket_commands(hass)
        await _async_register_services(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    async def _periodic_check(now) -> None:
        await _async_run_checks(hass, entry, store)

    remove_interval = async_track_time_interval(
        hass, _periodic_check, timedelta(minutes=CHECK_INTERVAL_MINUTES)
    )
    entry.async_on_unload(remove_interval)

    # Run once on startup too.
    await _async_run_checks(hass, entry, store)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Options (locations / warning days) changed - refresh sensors."""
    store: InventoryManagerStore = hass.data[DOMAIN][entry.entry_id]["store"]
    for location in entry.options.get(CONF_LOCATIONS, []):
        store.add_location(location)
    await store.async_save()
    async_dispatcher_send(hass, f"{SIGNAL_LOCATIONS_UPDATED}_{entry.entry_id}")
    async_dispatcher_send(hass, f"{SIGNAL_DATA_UPDATED}_{entry.entry_id}")


async def _async_register_frontend(hass: HomeAssistant) -> None:
    import os

    from homeassistant.components.frontend import add_extra_js_url
    from homeassistant.components.http import StaticPathConfig

    www_dir = os.path.join(os.path.dirname(__file__), "www")
    url = f"{STATIC_URL_BASE}/{CARD_FILENAME}"

    if not hass.data.get(f"{DOMAIN}_frontend_registered"):
        try:
            await hass.http.async_register_static_paths(
                [StaticPathConfig(STATIC_URL_BASE, www_dir, cache_headers=False)]
            )
        except AttributeError:
            # Older HA core fallback (pre 2024.7)
            hass.http.register_static_path(STATIC_URL_BASE, www_dir, cache_headers=False)

        add_extra_js_url(hass, f"{url}?v={CARD_VERSION}")
        hass.data[f"{DOMAIN}_frontend_registered"] = True


async def _async_run_checks(
    hass: HomeAssistant, entry: ConfigEntry, store: InventoryManagerStore
) -> None:
    """Fire events + repair issues for low stock / expiring items."""
    warning_days = entry.options.get(CONF_EXPIRY_WARNING_DAYS, DEFAULT_EXPIRY_WARNING_DAYS)

    low_stock = store.low_stock_items()
    if low_stock:
        hass.bus.async_fire(
            EVENT_LOW_STOCK,
            {"items": [{"item_id": i, **v} for i, v in low_stock.items()]},
        )
        async_create_issue(
            hass,
            DOMAIN,
            f"low_stock_{entry.entry_id}",
            is_fixable=False,
            severity=IssueSeverity.WARNING,
            translation_key="low_stock",
            translation_placeholders={
                "items": ", ".join(v["name"] for v in low_stock.values())
            },
        )
    else:
        async_delete_issue(hass, DOMAIN, f"low_stock_{entry.entry_id}")

    expiring = store.expiring_items(warning_days)
    if expiring:
        hass.bus.async_fire(
            EVENT_EXPIRING_SOON,
            {"items": [{"item_id": i, **v} for i, v in expiring.items()]},
        )
        async_create_issue(
            hass,
            DOMAIN,
            f"expiring_soon_{entry.entry_id}",
            is_fixable=False,
            severity=IssueSeverity.WARNING,
            translation_key="expiring_soon",
            translation_placeholders={
                "items": ", ".join(v["name"] for v in expiring.values())
            },
        )
    else:
        async_delete_issue(hass, DOMAIN, f"expiring_soon_{entry.entry_id}")


def _first_store(hass: HomeAssistant) -> tuple[str, InventoryManagerStore]:
    for entry_id, data in hass.data[DOMAIN].items():
        return entry_id, data["store"]
    raise RuntimeError("Inventory Manager is not set up")


async def _async_register_services(hass: HomeAssistant) -> None:
    async def _save_and_notify(entry_id: str, store: InventoryManagerStore) -> None:
        await store.async_save()
        async_dispatcher_send(hass, f"{SIGNAL_DATA_UPDATED}_{entry_id}")

    async def handle_add_item(call: ServiceCall) -> None:
        entry_id, store = _first_store(hass)
        store.add_item(
            name=call.data[ATTR_NAME],
            location=call.data[ATTR_LOCATION],
            quantity=call.data.get(ATTR_QUANTITY, 1),
            unit=call.data.get(ATTR_UNIT),
            expiration=call.data.get(ATTR_EXPIRATION),
            threshold=call.data.get(ATTR_THRESHOLD),
            category=call.data.get(ATTR_CATEGORY),
            notes=call.data.get(ATTR_NOTES),
        )
        async_dispatcher_send(hass, f"{SIGNAL_LOCATIONS_UPDATED}_{entry_id}")
        await _save_and_notify(entry_id, store)

    async def handle_update_item(call: ServiceCall) -> None:
        entry_id, store = _first_store(hass)
        data = dict(call.data)
        item_id = data.pop(ATTR_ITEM_ID)
        store.update_item(item_id, **data)
        await _save_and_notify(entry_id, store)

    async def handle_remove_item(call: ServiceCall) -> None:
        entry_id, store = _first_store(hass)
        store.remove_item(call.data[ATTR_ITEM_ID])
        await _save_and_notify(entry_id, store)

    async def handle_consume(call: ServiceCall) -> None:
        entry_id, store = _first_store(hass)
        store.adjust_quantity(call.data[ATTR_ITEM_ID], -call.data.get(ATTR_AMOUNT, 1))
        await _save_and_notify(entry_id, store)

    async def handle_restock(call: ServiceCall) -> None:
        entry_id, store = _first_store(hass)
        store.adjust_quantity(call.data[ATTR_ITEM_ID], call.data.get(ATTR_AMOUNT, 1))
        await _save_and_notify(entry_id, store)

    async def handle_add_location(call: ServiceCall) -> None:
        entry_id, store = _first_store(hass)
        store.add_location(call.data[ATTR_NAME])
        async_dispatcher_send(hass, f"{SIGNAL_LOCATIONS_UPDATED}_{entry_id}")
        await _save_and_notify(entry_id, store)

    async def handle_remove_location(call: ServiceCall) -> None:
        entry_id, store = _first_store(hass)
        store.remove_location(call.data[ATTR_NAME])
        await _save_and_notify(entry_id, store)

    hass.services.async_register(DOMAIN, SERVICE_ADD_ITEM, handle_add_item, schema=_ADD_ITEM_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_UPDATE_ITEM, handle_update_item, schema=_UPDATE_ITEM_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REMOVE_ITEM, handle_remove_item, schema=_ITEM_ID_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CONSUME, handle_consume, schema=_QUANTITY_CHANGE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_RESTOCK, handle_restock, schema=_QUANTITY_CHANGE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_ADD_LOCATION, handle_add_location, schema=_LOCATION_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REMOVE_LOCATION, handle_remove_location, schema=_LOCATION_SCHEMA)

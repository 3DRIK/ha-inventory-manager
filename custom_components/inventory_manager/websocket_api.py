"""WebSocket API used by the inventory-card frontend."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_EXPIRY_WARNING_DAYS,
    DEFAULT_EXPIRY_WARNING_DAYS,
    DOMAIN,
    SIGNAL_DATA_UPDATED,
    SIGNAL_LOCATIONS_UPDATED,
)
from .storage import InventoryManagerStore


def _get_store(hass: HomeAssistant, entry_id: str | None) -> tuple[str, InventoryManagerStore]:
    """Return (entry_id, store) - falls back to the single configured entry."""
    domain_data = hass.data.get(DOMAIN, {})
    if entry_id and entry_id in domain_data:
        return entry_id, domain_data[entry_id]["store"]
    # single-instance integration: just grab the only entry
    for eid, data in domain_data.items():
        return eid, data["store"]
    raise KeyError("no_config_entry")


def _notify_data_updated(hass: HomeAssistant, entry_id: str) -> None:
    async_dispatcher_send(hass, f"{SIGNAL_DATA_UPDATED}_{entry_id}")
    hass.bus.async_fire(f"{DOMAIN}_item_updated", {"entry_id": entry_id})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/get_data"})
@websocket_api.async_response
async def ws_get_data(hass: HomeAssistant, connection, msg) -> None:
    entry_id, store = _get_store(hass, None)
    entry = hass.config_entries.async_get_entry(entry_id)
    warning_days = (
        entry.options.get(CONF_EXPIRY_WARNING_DAYS, DEFAULT_EXPIRY_WARNING_DAYS)
        if entry
        else DEFAULT_EXPIRY_WARNING_DAYS
    )
    connection.send_result(
        msg["id"],
        {
            "entry_id": entry_id,
            "locations": store.locations,
            "items": store.as_item_list(store.items),
            "expiry_warning_days": warning_days,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/add_item",
        vol.Required("name"): str,
        vol.Required("location"): str,
        vol.Optional("quantity", default=1): vol.Coerce(float),
        vol.Optional("unit"): str,
        vol.Optional("expiration"): str,
        vol.Optional("threshold"): vol.Coerce(float),
        vol.Optional("category"): str,
        vol.Optional("notes"): str,
    }
)
@websocket_api.async_response
async def ws_add_item(hass: HomeAssistant, connection, msg) -> None:
    entry_id, store = _get_store(hass, None)
    item_id = store.add_item(
        name=msg["name"],
        location=msg["location"],
        quantity=msg.get("quantity", 1),
        unit=msg.get("unit"),
        expiration=msg.get("expiration"),
        threshold=msg.get("threshold"),
        category=msg.get("category"),
        notes=msg.get("notes"),
    )
    await store.async_save()
    _notify_data_updated(hass, entry_id)
    async_dispatcher_send(hass, f"{SIGNAL_LOCATIONS_UPDATED}_{entry_id}")
    connection.send_result(msg["id"], {"item_id": item_id})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/update_item",
        vol.Required("item_id"): str,
        vol.Optional("name"): str,
        vol.Optional("location"): str,
        vol.Optional("quantity"): vol.Coerce(float),
        vol.Optional("unit"): str,
        vol.Optional("expiration"): str,
        vol.Optional("threshold"): vol.Coerce(float),
        vol.Optional("category"): str,
        vol.Optional("notes"): str,
    }
)
@websocket_api.async_response
async def ws_update_item(hass: HomeAssistant, connection, msg) -> None:
    entry_id, store = _get_store(hass, None)
    data = {k: v for k, v in msg.items() if k not in ("type", "id", "item_id")}
    try:
        store.update_item(msg["item_id"], **data)
    except KeyError:
        connection.send_error(msg["id"], "not_found", "Item not found")
        return
    await store.async_save()
    _notify_data_updated(hass, entry_id)
    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/remove_item", vol.Required("item_id"): str}
)
@websocket_api.async_response
async def ws_remove_item(hass: HomeAssistant, connection, msg) -> None:
    entry_id, store = _get_store(hass, None)
    store.remove_item(msg["item_id"])
    await store.async_save()
    _notify_data_updated(hass, entry_id)
    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/adjust_quantity",
        vol.Required("item_id"): str,
        vol.Required("delta"): vol.Coerce(float),
    }
)
@websocket_api.async_response
async def ws_adjust_quantity(hass: HomeAssistant, connection, msg) -> None:
    entry_id, store = _get_store(hass, None)
    try:
        new_qty = store.adjust_quantity(msg["item_id"], msg["delta"])
    except KeyError:
        connection.send_error(msg["id"], "not_found", "Item not found")
        return
    await store.async_save()
    _notify_data_updated(hass, entry_id)
    connection.send_result(msg["id"], {"quantity": new_qty})


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/add_location", vol.Required("name"): str}
)
@websocket_api.async_response
async def ws_add_location(hass: HomeAssistant, connection, msg) -> None:
    entry_id, store = _get_store(hass, None)
    store.add_location(msg["name"])
    await store.async_save()
    async_dispatcher_send(hass, f"{SIGNAL_LOCATIONS_UPDATED}_{entry_id}")
    _notify_data_updated(hass, entry_id)
    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/rename_location",
        vol.Required("old_name"): str,
        vol.Required("new_name"): str,
    }
)
@websocket_api.async_response
async def ws_rename_location(hass: HomeAssistant, connection, msg) -> None:
    entry_id, store = _get_store(hass, None)
    store.rename_location(msg["old_name"], msg["new_name"])
    await store.async_save()
    async_dispatcher_send(hass, f"{SIGNAL_LOCATIONS_UPDATED}_{entry_id}")
    _notify_data_updated(hass, entry_id)
    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/remove_location", vol.Required("name"): str}
)
@websocket_api.async_response
async def ws_remove_location(hass: HomeAssistant, connection, msg) -> None:
    entry_id, store = _get_store(hass, None)
    store.remove_location(msg["name"])
    await store.async_save()
    _notify_data_updated(hass, entry_id)
    connection.send_result(msg["id"], {"success": True})


def async_register_websocket_commands(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_get_data)
    websocket_api.async_register_command(hass, ws_add_item)
    websocket_api.async_register_command(hass, ws_update_item)
    websocket_api.async_register_command(hass, ws_remove_item)
    websocket_api.async_register_command(hass, ws_adjust_quantity)
    websocket_api.async_register_command(hass, ws_add_location)
    websocket_api.async_register_command(hass, ws_rename_location)
    websocket_api.async_register_command(hass, ws_remove_location)
"""Persistent storage + business logic for Inventory Manager."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    DEFAULT_LOCATIONS,
    STORAGE_KEY_TEMPLATE,
    STORAGE_VERSION,
)


def _today() -> date:
    return datetime.now().date()


class InventoryManagerStore:
    """Owns the persisted state (locations + items) for one config entry.

    Data layout on disk:
    {
        "locations": ["Špajza", "Chladnička", ...],
        "items": {
            "<item_id>": {
                "name": str,
                "location": str,
                "quantity": float,
                "unit": str | None,
                "expiration": "YYYY-MM-DD" | None,
                "threshold": float | None,
                "category": str | None,
                "notes": str | None,
            },
            ...
        }
    }
    """

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self._store: Store = Store(
            hass, STORAGE_VERSION, STORAGE_KEY_TEMPLATE.format(entry_id=entry_id)
        )
        self.locations: list[str] = list(DEFAULT_LOCATIONS)
        self.items: dict[str, dict[str, Any]] = {}

    async def async_load(self, default_locations: list[str] | None = None) -> None:
        data = await self._store.async_load()
        if data is None:
            self.locations = list(default_locations or DEFAULT_LOCATIONS)
            self.items = {}
            await self.async_save()
            return
        self.locations = data.get("locations", list(default_locations or DEFAULT_LOCATIONS))
        self.items = data.get("items", {})

    async def async_save(self) -> None:
        await self._store.async_save(
            {"locations": self.locations, "items": self.items}
        )

    # ------------------------------------------------------------------
    # Locations
    # ------------------------------------------------------------------
    def add_location(self, name: str) -> None:
        name = name.strip()
        if name and name not in self.locations:
            self.locations.append(name)

    def remove_location(self, name: str, *, reassign_to: str | None = None) -> None:
        if name not in self.locations:
            return
        self.locations.remove(name)
        for item in self.items.values():
            if item["location"] == name:
                item["location"] = reassign_to or (
                    self.locations[0] if self.locations else "Nezaradené"
                )

    # ------------------------------------------------------------------
    # Items
    # ------------------------------------------------------------------
    def add_item(
        self,
        name: str,
        location: str,
        quantity: float = 1,
        unit: str | None = None,
        expiration: str | None = None,
        threshold: float | None = None,
        category: str | None = None,
        notes: str | None = None,
    ) -> str:
        if location not in self.locations:
            self.add_location(location)
        item_id = uuid.uuid4().hex[:8]
        self.items[item_id] = {
            "name": name,
            "location": location,
            "quantity": quantity,
            "unit": unit,
            "expiration": expiration,
            "threshold": threshold,
            "category": category,
            "notes": notes,
        }
        return item_id

    def update_item(self, item_id: str, **fields: Any) -> None:
        if item_id not in self.items:
            raise KeyError(item_id)
        allowed = {
            "name",
            "location",
            "quantity",
            "unit",
            "expiration",
            "threshold",
            "category",
            "notes",
        }
        for key, value in fields.items():
            if key in allowed and value is not None:
                self.items[item_id][key] = value

    def remove_item(self, item_id: str) -> None:
        self.items.pop(item_id, None)

    def find_item_id(self, name: str, location: str | None = None) -> str | None:
        for item_id, item in self.items.items():
            if item["name"].lower() == name.lower() and (
                location is None or item["location"] == location
            ):
                return item_id
        return None

    def adjust_quantity(self, item_id: str, delta: float, *, floor_zero: bool = True) -> float:
        if item_id not in self.items:
            raise KeyError(item_id)
        new_qty = self.items[item_id]["quantity"] + delta
        if floor_zero and new_qty < 0:
            new_qty = 0
        self.items[item_id]["quantity"] = new_qty
        return new_qty

    # ------------------------------------------------------------------
    # Derived views
    # ------------------------------------------------------------------
    def items_for_location(self, location: str) -> dict[str, dict[str, Any]]:
        return {
            iid: item for iid, item in self.items.items() if item["location"] == location
        }

    def low_stock_items(self, location: str | None = None) -> dict[str, dict[str, Any]]:
        result = {}
        for iid, item in self.items.items():
            if location is not None and item["location"] != location:
                continue
            threshold = item.get("threshold")
            if threshold is not None and item["quantity"] <= threshold:
                result[iid] = item
        return result

    def expiring_items(
        self, warning_days: int, location: str | None = None
    ) -> dict[str, dict[str, Any]]:
        result = {}
        cutoff = _today() + timedelta(days=warning_days)
        for iid, item in self.items.items():
            if location is not None and item["location"] != location:
                continue
            exp = item.get("expiration")
            if not exp:
                continue
            try:
                exp_date = date.fromisoformat(exp)
            except ValueError:
                continue
            if exp_date <= cutoff:
                result[iid] = item
        return result

    def expired_items(self, location: str | None = None) -> dict[str, dict[str, Any]]:
        result = {}
        today = _today()
        for iid, item in self.items.items():
            if location is not None and item["location"] != location:
                continue
            exp = item.get("expiration")
            if not exp:
                continue
            try:
                exp_date = date.fromisoformat(exp)
            except ValueError:
                continue
            if exp_date < today:
                result[iid] = item
        return result

    def as_item_list(self, items: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        return [{"item_id": iid, **item} for iid, item in items.items()]

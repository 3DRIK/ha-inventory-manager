"""Constants for the Inventory Manager integration."""
from __future__ import annotations

DOMAIN = "inventory_manager"
PLATFORMS = ["sensor"]

STORAGE_VERSION = 1
STORAGE_KEY_TEMPLATE = "inventory_manager_{entry_id}"

# Config / options keys
CONF_LOCATIONS = "locations"
CONF_EXPIRY_WARNING_DAYS = "expiry_warning_days"
DEFAULT_EXPIRY_WARNING_DAYS = 7
DEFAULT_LOCATIONS = ["Špajza", "Chladnička", "Mraznička"]

# Item dict keys
ATTR_ITEM_ID = "item_id"
ATTR_NAME = "name"
ATTR_LOCATION = "location"
ATTR_QUANTITY = "quantity"
ATTR_UNIT = "unit"
ATTR_EXPIRATION = "expiration"
ATTR_THRESHOLD = "threshold"
ATTR_CATEGORY = "category"
ATTR_NOTES = "notes"
ATTR_AMOUNT = "amount"

# Signals
SIGNAL_DATA_UPDATED = f"{DOMAIN}_data_updated"
SIGNAL_LOCATIONS_UPDATED = f"{DOMAIN}_locations_updated"

# Events fired on the HA event bus (usable in automations)
EVENT_LOW_STOCK = f"{DOMAIN}_low_stock"
EVENT_EXPIRING_SOON = f"{DOMAIN}_expiring_soon"
EVENT_ITEM_UPDATED = f"{DOMAIN}_item_updated"

# Periodic check interval (minutes) for low-stock / expiration events
CHECK_INTERVAL_MINUTES = 60

STATIC_URL_BASE = "/inventory_manager_static"
CARD_FILENAME = "inventory-card.js"
CARD_VERSION = "1.2.0"
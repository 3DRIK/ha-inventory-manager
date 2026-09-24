"""Config flow for Inventory Manager."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    CONF_EXPIRY_WARNING_DAYS,
    CONF_LOCATIONS,
    DEFAULT_EXPIRY_WARNING_DAYS,
    DEFAULT_LOCATIONS,
    DOMAIN,
)


def _parse_locations(raw: str) -> list[str]:
    return [loc.strip() for loc in raw.split(",") if loc.strip()]


class InventoryManagerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial setup - single instance only."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors: dict[str, str] = {}
        if user_input is not None:
            locations = _parse_locations(user_input[CONF_LOCATIONS])
            if not locations:
                errors["base"] = "no_locations"
            else:
                return self.async_create_entry(
                    title="Inventory Manager",
                    data={},
                    options={
                        CONF_LOCATIONS: locations,
                        CONF_EXPIRY_WARNING_DAYS: user_input[CONF_EXPIRY_WARNING_DAYS],
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_LOCATIONS, default=", ".join(DEFAULT_LOCATIONS)
                ): str,
                vol.Required(
                    CONF_EXPIRY_WARNING_DAYS, default=DEFAULT_EXPIRY_WARNING_DAYS
                ): vol.Coerce(int),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> InventoryManagerOptionsFlow:
        return InventoryManagerOptionsFlow(config_entry)


class InventoryManagerOptionsFlow(config_entries.OptionsFlow):
    """Manage locations and warning threshold after setup."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        current_locations = self._config_entry.options.get(
            CONF_LOCATIONS, DEFAULT_LOCATIONS
        )
        current_days = self._config_entry.options.get(
            CONF_EXPIRY_WARNING_DAYS, DEFAULT_EXPIRY_WARNING_DAYS
        )

        if user_input is not None:
            locations = _parse_locations(user_input[CONF_LOCATIONS])
            if not locations:
                errors["base"] = "no_locations"
            else:
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_LOCATIONS: locations,
                        CONF_EXPIRY_WARNING_DAYS: user_input[
                            CONF_EXPIRY_WARNING_DAYS
                        ],
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_LOCATIONS, default=", ".join(current_locations)
                ): str,
                vol.Required(
                    CONF_EXPIRY_WARNING_DAYS, default=current_days
                ): vol.Coerce(int),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

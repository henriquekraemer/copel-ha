"""The Copel integration."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CopelAuthError, CopelClient, CopelError
from .const import CONF_DOCUMENTO, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import CopelConfigEntry, CopelCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: CopelConfigEntry) -> bool:
    """Set up Copel from a config entry."""
    client = CopelClient(
        async_get_clientsession(hass),
        entry.data[CONF_DOCUMENTO],
        entry.data[CONF_PASSWORD],
    )

    try:
        await client.async_login()
    except CopelAuthError as err:
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN, translation_key="invalid_auth"
        ) from err
    except CopelError as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
            translation_placeholders={"error": str(err)},
        ) from err

    coordinator = CopelCoordinator(
        hass,
        entry,
        client,
        entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: CopelConfigEntry) -> None:
    """Handle options update."""
    coordinator = entry.runtime_data
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    if coordinator.update_interval != timedelta(seconds=scan_interval):
        coordinator.update_interval = timedelta(seconds=scan_interval)
        await coordinator.async_request_refresh()


async def async_unload_entry(hass: HomeAssistant, entry: CopelConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: CopelConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Allow removing a UC device the portal no longer reports."""
    return not any(
        identifier[0] == DOMAIN and identifier[1] in entry.runtime_data.data
        for identifier in device_entry.identifiers
    )

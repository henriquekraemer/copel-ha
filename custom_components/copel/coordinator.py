"""DataUpdateCoordinator for Copel."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    CopelApiError,
    CopelAuthError,
    CopelClient,
    CopelConnectionError,
    CopelUcData,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

type CopelConfigEntry = ConfigEntry[CopelCoordinator]


class CopelCoordinator(DataUpdateCoordinator[dict[str, CopelUcData]]):
    """Scrape consumption and invoices for every UC on the account."""

    config_entry: CopelConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: CopelConfigEntry,
        client: CopelClient,
        scan_interval: int,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, CopelUcData]:
        try:
            data = await self.client.async_get_all_data()
        except CopelAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN,
                translation_key="invalid_auth",
            ) from err
        except CopelConnectionError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"error": str(err)},
            ) from err
        except CopelApiError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="unexpected_response",
                translation_placeholders={"error": str(err)},
            ) from err

        if self.data is not None:
            for codigo in data.keys() - self.data.keys():
                _LOGGER.info("New consumer unit found: %s", codigo)
        return data

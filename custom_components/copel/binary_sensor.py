"""Binary sensor platform for Copel.

For now this exposes an "invoice overdue" sensor derived from the billing data.
A real-time "falta de energia" (power outage) sensor is planned once the public
outage-status endpoint is mapped — see docs/recon-ava-web.md.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import CopelUcData
from .coordinator import CopelConfigEntry, CopelCoordinator
from .entity import CopelEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class CopelBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a Copel binary sensor."""

    value_fn: Callable[[CopelUcData], bool]


def _fatura_em_atraso(data: CopelUcData) -> bool:
    fatura = data.fatura_atual
    return bool(fatura and fatura.dias_atraso and fatura.dias_atraso > 0)


SENSORS: tuple[CopelBinarySensorDescription, ...] = (
    CopelBinarySensorDescription(
        key="fatura_em_atraso",
        translation_key="fatura_em_atraso",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=_fatura_em_atraso,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CopelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Copel binary sensors."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _async_add_new() -> None:
        new = [codigo for codigo in coordinator.data if codigo not in known]
        if not new:
            return
        known.update(new)
        async_add_entities(
            CopelBinarySensor(coordinator, codigo, description)
            for codigo in new
            for description in SENSORS
        )

    _async_add_new()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new))


class CopelBinarySensor(CopelEntity, BinarySensorEntity):
    """A Copel binary sensor."""

    entity_description: CopelBinarySensorDescription

    def __init__(
        self,
        coordinator: CopelCoordinator,
        uc_codigo: str,
        description: CopelBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, uc_codigo)
        self.entity_description = description
        self._attr_unique_id = f"{uc_codigo}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return the state of the sensor."""
        data = self.uc_data
        return None if data is None else self.entity_description.value_fn(data)

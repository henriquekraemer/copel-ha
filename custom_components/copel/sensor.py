"""Sensor platform for Copel."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .api import CopelUcData
from .const import (
    ATTR_NUMERO_FATURA,
    ATTR_ORIGEM,
    ATTR_REFERENCIA,
    ATTR_SITUACAO,
)
from .coordinator import CopelConfigEntry, CopelCoordinator
from .entity import CopelEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class CopelSensorDescription(SensorEntityDescription):
    """Describes a Copel sensor."""

    value_fn: Callable[[CopelUcData], StateType | date]
    attr_fn: Callable[[CopelUcData], dict[str, Any]] | None = None


def _consumo_kwh(data: CopelUcData, index: int) -> int | None:
    if index < len(data.consumo):
        return data.consumo[index].consumo_kwh
    return None


SENSORS: tuple[CopelSensorDescription, ...] = (
    CopelSensorDescription(
        key="consumo_atual",
        translation_key="consumo_atual",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda d: _consumo_kwh(d, 0),
        attr_fn=lambda d: (
            {ATTR_REFERENCIA: d.consumo_atual.referencia} if d.consumo_atual else {}
        ),
    ),
    CopelSensorDescription(
        key="consumo_anterior",
        translation_key="consumo_anterior",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        entity_registry_enabled_default=False,
        value_fn=lambda d: _consumo_kwh(d, 1),
        attr_fn=lambda d: (
            {ATTR_REFERENCIA: d.consumo[1].referencia} if len(d.consumo) > 1 else {}
        ),
    ),
    CopelSensorDescription(
        key="fatura_valor",
        translation_key="fatura_valor",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="BRL",
        value_fn=lambda d: (
            float(d.fatura_atual.valor)
            if d.fatura_atual and d.fatura_atual.valor is not None
            else None
        ),
        attr_fn=lambda d: (
            {
                ATTR_REFERENCIA: d.fatura_atual.referencia,
                ATTR_NUMERO_FATURA: d.fatura_atual.numero,
                ATTR_ORIGEM: d.fatura_atual.origem,
                ATTR_SITUACAO: d.fatura_atual.situacao,
            }
            if d.fatura_atual
            else {}
        ),
    ),
    CopelSensorDescription(
        key="fatura_vencimento",
        translation_key="fatura_vencimento",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda d: d.fatura_atual.vencimento if d.fatura_atual else None,
    ),
    CopelSensorDescription(
        key="total_debitos",
        translation_key="total_debitos",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="BRL",
        value_fn=lambda d: (
            float(d.total_debitos) if d.total_debitos is not None else None
        ),
    ),
    CopelSensorDescription(
        key="dias_atraso",
        translation_key="dias_atraso",
        native_unit_of_measurement="d",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: (
            d.fatura_atual.dias_atraso
            if d.fatura_atual and d.fatura_atual.dias_atraso is not None
            else 0
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CopelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Copel sensors."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _async_add_new() -> None:
        new = [codigo for codigo in coordinator.data if codigo not in known]
        if not new:
            return
        known.update(new)
        async_add_entities(
            CopelSensor(coordinator, codigo, description)
            for codigo in new
            for description in SENSORS
        )

    _async_add_new()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new))


class CopelSensor(CopelEntity, SensorEntity):
    """A Copel sensor."""

    entity_description: CopelSensorDescription

    def __init__(
        self,
        coordinator: CopelCoordinator,
        uc_codigo: str,
        description: CopelSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, uc_codigo)
        self.entity_description = description
        self._attr_unique_id = f"{uc_codigo}_{description.key}"

    @property
    def native_value(self) -> StateType | date:
        """Return the sensor value."""
        data = self.uc_data
        return None if data is None else self.entity_description.value_fn(data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes for the sensor."""
        data = self.uc_data
        if data is None or self.entity_description.attr_fn is None:
            return None
        return {
            k: v
            for k, v in self.entity_description.attr_fn(data).items()
            if v is not None
        }

"""Base entity for Copel."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import CopelUcData
from .const import API_BASE_URL, DOMAIN, MANUFACTURER
from .coordinator import CopelCoordinator


class CopelEntity(CoordinatorEntity[CopelCoordinator]):
    """Base class for Copel entities, one device per consumer unit (UC)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: CopelCoordinator, uc_codigo: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._uc_codigo = uc_codigo
        uc = coordinator.data[uc_codigo].uc
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, uc_codigo)},
            name=uc.endereco or f"UC {uc_codigo}",
            manufacturer=MANUFACTURER,
            model=f"Grupo {uc.grupo}" if uc.grupo else None,
            serial_number=uc_codigo,
            suggested_area=uc.cidade,
            configuration_url=API_BASE_URL,
        )

    @property
    def uc_data(self) -> CopelUcData | None:
        """Return the scraped data for this UC from the last update."""
        return self.coordinator.data.get(self._uc_codigo)

    @property
    def available(self) -> bool:
        """Return True if the UC is still reported by the portal."""
        return super().available and self.uc_data is not None

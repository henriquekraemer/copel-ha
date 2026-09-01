"""Diagnostics support for Copel."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .const import CONF_DOCUMENTO
from .coordinator import CopelConfigEntry

TO_REDACT = {
    CONF_DOCUMENTO,
    CONF_PASSWORD,
    "documento",
    "senha",
    "codigo",
    "codigo_antigo",
    "endereco",
    "numero",
    "fatura",
    "unique_id",
    "title",
}


def _uc_to_dict(data: Any) -> dict[str, Any]:
    raw = asdict(data)
    # Decimal/date are not JSON-serialisable; stringify for the report.
    for fatura in raw.get("faturas", []):
        for key, value in list(fatura.items()):
            if value is not None and not isinstance(value, (str, int, float, bool)):
                fatura[key] = str(value)
    if raw.get("total_debitos") is not None:
        raw["total_debitos"] = str(raw["total_debitos"])
    return raw


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: CopelConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval
                else None
            ),
            "uc_count": len(coordinator.data) if coordinator.data else 0,
        },
        "ucs": async_redact_data(
            [_uc_to_dict(uc_data) for uc_data in (coordinator.data or {}).values()],
            TO_REDACT,
        ),
    }

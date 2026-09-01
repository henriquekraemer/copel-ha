"""Config flow for Copel."""

from __future__ import annotations

from collections.abc import Mapping
import logging
import re
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import voluptuous as vol

from .api import CopelAuthError, CopelClient, CopelConnectionError, CopelError
from .const import (
    CONF_DOCUMENTO,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

_DOCUMENTO_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT))
_PASSWORD_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DOCUMENTO): _DOCUMENTO_SELECTOR,
        vol.Required(CONF_PASSWORD): _PASSWORD_SELECTOR,
    }
)
STEP_REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): _PASSWORD_SELECTOR})


def _normalize_documento(documento: str) -> str:
    return re.sub(r"\D", "", documento)


async def _async_validate(
    hass: HomeAssistant, documento: str, senha: str
) -> str | None:
    """Return an error key if login fails, None otherwise."""
    client = CopelClient(async_get_clientsession(hass), documento, senha)
    try:
        await client.async_login()
    except CopelAuthError:
        return "invalid_auth"
    except CopelConnectionError:
        return "cannot_connect"
    except CopelError:
        _LOGGER.exception("Unexpected error validating Copel credentials")
        return "unknown"
    return None


class CopelConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Copel."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            documento = _normalize_documento(user_input[CONF_DOCUMENTO])
            senha = user_input[CONF_PASSWORD]

            await self.async_set_unique_id(documento)
            self._abort_if_unique_id_configured()

            error = await _async_validate(self.hass, documento, senha)
            if error is None:
                return self.async_create_entry(
                    title=f"Copel {documento}",
                    data={CONF_DOCUMENTO: documento, CONF_PASSWORD: senha},
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauth."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reauth confirmation."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            error = await _async_validate(
                self.hass, entry.data[CONF_DOCUMENTO], user_input[CONF_PASSWORD]
            )
            if error is None:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_SCHEMA,
            description_placeholders={CONF_DOCUMENTO: entry.data[CONF_DOCUMENTO]},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of the account credentials."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            documento = _normalize_documento(user_input[CONF_DOCUMENTO])
            await self.async_set_unique_id(documento)
            self._abort_if_unique_id_mismatch(reason="wrong_account")

            error = await _async_validate(
                self.hass, documento, user_input[CONF_PASSWORD]
            )
            if error is None:
                return self.async_update_reload_and_abort(
                    entry,
                    title=f"Copel {documento}",
                    data_updates={
                        CONF_DOCUMENTO: documento,
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA,
                user_input or {CONF_DOCUMENTO: entry.data[CONF_DOCUMENTO]},
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> CopelOptionsFlow:
        """Get the options flow."""
        return CopelOptionsFlow()


class CopelOptionsFlow(OptionsFlow):
    """Handle Copel options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL])}
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=60,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

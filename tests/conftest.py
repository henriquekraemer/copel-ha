"""Fixtures for Copel tests."""

from __future__ import annotations

from collections.abc import Callable
import pathlib

from homeassistant.const import CONF_PASSWORD
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.copel.const import CONF_DOCUMENTO, DOMAIN

_FIXTURES = pathlib.Path(__file__).parent / "fixtures"

TEST_DOCUMENTO = "12345678909"
TEST_SENHA = "hunter2"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations."""


@pytest.fixture
def load_fixture() -> Callable[[str], str]:
    """Return a helper that reads an HTML fixture by name."""

    def _load(name: str) -> str:
        return (_FIXTURES / name).read_text(encoding="utf-8")

    return _load


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=f"Copel {TEST_DOCUMENTO}",
        unique_id=TEST_DOCUMENTO,
        data={CONF_DOCUMENTO: TEST_DOCUMENTO, CONF_PASSWORD: TEST_SENHA},
    )

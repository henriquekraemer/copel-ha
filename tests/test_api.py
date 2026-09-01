"""Tests for the Copel scraping client parsers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal

import pytest

from custom_components.copel.api import (
    CopelApiError,
    CopelClient,
    _parse_data,
    _parse_referencia,
    _parse_valor,
    parse_consumo,
    parse_faturas,
    parse_ucs,
)


def test_parse_ucs(load_fixture: Callable[[str], str]) -> None:
    ucs = parse_ucs(load_fixture("listar_ucs.html"))
    assert [uc.codigo for uc in ucs] == ["100000000001", "100000000002"]
    first = ucs[0]
    assert first.codigo_antigo == "10000001"
    assert first.cidade == "CURITIBA - PR"
    assert first.endereco == "RUA EXEMPLO, 100"
    assert first.grupo == "B"
    assert first.situacao == "LG"
    assert first.row_index == 0
    assert ucs[1].row_index == 1


def test_parse_consumo(load_fixture: Callable[[str], str]) -> None:
    consumo = parse_consumo(load_fixture("consumo.html"))
    assert len(consumo) == 3
    first = consumo[0]
    assert first.referencia == "08/2026"
    assert (first.ano, first.mes) == (2026, 8)
    assert first.fatura == "90000000000001"
    assert first.consumo_kwh == 100
    assert consumo[1].consumo_kwh == 210


def test_parse_faturas(load_fixture: Callable[[str], str]) -> None:
    faturas, total = parse_faturas(load_fixture("debitos.html"))
    assert len(faturas) == 1
    fatura = faturas[0]
    assert fatura.referencia == "08/2026"
    assert fatura.numero == "90000000000001"
    assert fatura.situacao == "AB"
    assert fatura.origem == "FATURAMENTO NORMAL"
    assert fatura.vencimento == date(2026, 9, 4)
    assert fatura.dias_atraso is None
    assert fatura.valor == Decimal("199.90")
    assert total == Decimal("199.90")


def test_missing_table_raises() -> None:
    with pytest.raises(CopelApiError):
        parse_consumo("<html><body>sem tabela</body></html>")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.234,56", Decimal("1234.56")),
        ("R$ 199,90", Decimal("199.90")),
        ("0,00", Decimal("0.00")),
        ("", None),
        ("-", None),
    ],
)
def test_parse_valor(raw: str, expected: Decimal | None) -> None:
    assert _parse_valor(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("08/2026", (2026, 8)),
        ("12/2025", (2025, 12)),
        ("13/2025", None),
        ("nada", None),
    ],
)
def test_parse_referencia(raw: str, expected: tuple[int, int] | None) -> None:
    assert _parse_referencia(raw) == expected


def test_parse_data() -> None:
    assert _parse_data("04/09/2026") == date(2026, 9, 4)
    assert _parse_data("sem data") is None


def test_login_form(load_fixture: Callable[[str], str]) -> None:
    action, hidden, doc_field, pwd_field = CopelClient._login_form(
        load_fixture("login.html")
    )
    assert action == "/avaweb/paginaLogin/login.jsf;jsessionid=FAKE-SESSION-ID.node-1"
    assert doc_field == "formulario:numDoc"
    assert pwd_field == "formulario:pass"
    # ViewState, the form id and the submit button are all posted back by JSF.
    assert hidden["javax.faces.ViewState"] == "FAKE-VIEWSTATE-TOKEN"
    assert hidden["formulario"] == "formulario"
    assert hidden["formulario:j_idt41"] == "Entrar"


def test_login_form_without_password_raises() -> None:
    with pytest.raises(CopelApiError):
        CopelClient._login_form("<html><body><form></form></body></html>")

"""Client for the Copel Agência Virtual de Atendimento (AVA).

The AVA is a JSF/PrimeFaces application: there is no JSON API. Pages are
server-rendered HTML and data lives in PrimeFaces DataTables. This client keeps
a cookie session, drives the JSF form flow (handling ``javax.faces.ViewState``)
and parses the HTML tables into typed dataclasses.

The parsing functions (``parse_ucs``, ``parse_consumo``, ``parse_faturas``) are
pure and unit-tested against fixed HTML, so a layout change is caught by the
tests rather than in production.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
import logging
import re

import aiohttp
from bs4 import BeautifulSoup

from .const import API_ORIGIN, API_TIMEOUT_SECONDS

_LOGGER = logging.getLogger(__name__)

# Pages of the AVA (site-absolute paths from the origin).
_LOGIN_PATH = "/avaweb/paginaLogin/login.jsf"
_LIST_UCS_PATH = "/avaweb/paginas/listarUcsDoc.jsf"
_CONSUMO_PATH = "/avaweb/paginas/historicoConsumoGrupoB.jsf"
_DEBITOS_PATH = "/avaweb/paginas/consultaDebitos.jsf"

_VIEWSTATE = "javax.faces.ViewState"

# The AVA is a public consumer portal; send browser-like headers so it does not
# refuse a bare client. Kept minimal and honest (no spoofed brand).
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}


class CopelError(Exception):
    """Base exception for the client."""


class CopelAuthError(CopelError):
    """Credentials rejected."""


class CopelConnectionError(CopelError):
    """Portal unreachable or returned a server error."""


class CopelApiError(CopelError):
    """Unexpected response from the portal (e.g. a layout change)."""


@dataclass(frozen=True, slots=True)
class CopelUc:
    """A consumer unit (Unidade Consumidora) as listed by the AVA."""

    codigo: str  # UC ANEEL (12 digits) — the unique id
    codigo_antigo: str | None
    cidade: str | None
    endereco: str | None
    grupo: str | None  # e.g. "B" (residential)
    situacao: str | None  # e.g. "LG" (ligada)
    row_index: int  # position in the AVA table, used to select it


@dataclass(frozen=True, slots=True)
class ConsumoMes:
    """One month of consumption from the Histórico de consumo table."""

    referencia: str  # "MM/AAAA"
    ano: int
    mes: int
    fatura: str | None
    consumo_kwh: int


@dataclass(frozen=True, slots=True)
class Fatura:
    """One invoice/debt row from the Consulta de débitos table."""

    referencia: str  # "MM/AAAA"
    numero: str | None
    situacao: str | None  # e.g. "AB" (aberta)
    origem: str | None
    vencimento: date | None
    dias_atraso: int | None
    valor: Decimal | None  # R$


@dataclass(frozen=True, slots=True)
class CopelUcData:
    """Everything scraped for a single UC in one refresh."""

    uc: CopelUc
    consumo: list[ConsumoMes] = field(default_factory=list)
    faturas: list[Fatura] = field(default_factory=list)
    total_debitos: Decimal | None = None

    @property
    def consumo_atual(self) -> ConsumoMes | None:
        """Most recent month of consumption, if any."""
        return self.consumo[0] if self.consumo else None

    @property
    def fatura_atual(self) -> Fatura | None:
        """Most recent invoice, if any."""
        return self.faturas[0] if self.faturas else None


# ---------------------------------------------------------------------------
# Pure parsing helpers
# ---------------------------------------------------------------------------


def _clean(text: str) -> str:
    return " ".join(text.split()).strip()


def _text_or_none(value: str) -> str | None:
    value = _clean(value)
    return value or None


def _parse_referencia(value: str) -> tuple[int, int] | None:
    """Parse "MM/AAAA" -> (ano, mes)."""
    match = re.search(r"(\d{1,2})\s*/\s*(\d{4})", value)
    if not match:
        return None
    mes, ano = int(match.group(1)), int(match.group(2))
    if not 1 <= mes <= 12:
        return None
    return ano, mes


def _parse_int(value: str) -> int | None:
    digits = re.sub(r"[^\d-]", "", value)
    if not digits or digits == "-":
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def _parse_valor(value: str) -> Decimal | None:
    """Parse a Brazilian currency string like "1.234,56" -> Decimal."""
    cleaned = re.sub(r"[^\d.,]", "", value)
    if not cleaned:
        return None
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _parse_data(value: str) -> date | None:
    match = re.search(r"(\d{2})/(\d{2})/(\d{4})", value)
    if not match:
        return None
    day, month, year = (int(g) for g in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _dedupe(items: list[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.append(item)
    return seen


def _find_datatable(
    soup: BeautifulSoup, required_headers: list[str]
) -> tuple[list[str], list[list[str]]]:
    """Find the first data table matching ``required_headers`` and return it.

    Matches headers case-insensitively as substrings. Works both for a plain
    ``<table>`` and for a PrimeFaces ``.ui-datatable`` container, which in
    scrollable mode splits the header and the body into separate inner tables.
    Returns (headers, rows); each row is a list of cell texts. Raises
    CopelApiError if nothing matches (a layout change is loud, not silent).
    """
    required = [h.lower() for h in required_headers]
    containers = soup.select(".ui-datatable") or soup.find_all("table")
    for container in containers:
        headers = _dedupe(
            [_clean(th.get_text()) for th in container.select("thead th")]
        )
        low = [h.lower() for h in headers]
        if not headers or not all(any(req in h for h in low) for req in required):
            continue
        rows: list[list[str]] = []
        for tr in container.select("tbody tr"):
            cells = tr.find_all("td", recursive=False)
            if cells:
                rows.append([_clean(td.get_text()) for td in cells])
        return headers, rows
    raise CopelApiError(
        f"No table matching headers {required_headers!r} found (layout changed?)"
    )


def _col(headers: list[str], substr: str) -> int | None:
    substr = substr.lower()
    for index, header in enumerate(headers):
        if substr in header.lower():
            return index
    return None


def parse_ucs(html: str) -> list[CopelUc]:
    """Parse the ``listarUcsDoc.jsf`` table into a list of UCs."""
    soup = BeautifulSoup(html, "html.parser")
    headers, rows = _find_datatable(soup, ["consumidora aneel"])
    i_aneel = _col(headers, "aneel")
    i_antiga = _col(headers, "antiga")
    i_cidade = _col(headers, "cidade")
    i_end = _col(headers, "endere")
    i_grupo = _col(headers, "grupo")
    i_sit = _col(headers, "situa")

    def cell(row: list[str], index: int | None) -> str | None:
        if index is None or index >= len(row):
            return None
        return _text_or_none(row[index])

    ucs: list[CopelUc] = []
    for position, row in enumerate(rows):
        codigo = cell(row, i_aneel)
        if not codigo:
            continue
        codigo = re.sub(r"\D", "", codigo)
        ucs.append(
            CopelUc(
                codigo=codigo,
                codigo_antigo=cell(row, i_antiga),
                cidade=cell(row, i_cidade),
                endereco=cell(row, i_end),
                grupo=cell(row, i_grupo),
                situacao=cell(row, i_sit),
                row_index=position,
            )
        )
    return ucs


def parse_consumo(html: str) -> list[ConsumoMes]:
    """Parse the ``historicoConsumoGrupoB.jsf`` table into monthly consumption."""
    soup = BeautifulSoup(html, "html.parser")
    headers, rows = _find_datatable(soup, ["referência", "consumo"])
    i_ref = _col(headers, "refer")
    i_fatura = _col(headers, "fatura")
    i_kwh = _col(headers, "consumo")

    result: list[ConsumoMes] = []
    for row in rows:
        if i_ref is None or i_kwh is None or i_ref >= len(row) or i_kwh >= len(row):
            continue
        ref = _clean(row[i_ref])
        parsed = _parse_referencia(ref)
        kwh = _parse_int(row[i_kwh])
        if parsed is None or kwh is None:
            continue
        ano, mes = parsed
        fatura = (
            _text_or_none(row[i_fatura])
            if i_fatura is not None and i_fatura < len(row)
            else None
        )
        result.append(
            ConsumoMes(
                referencia=f"{mes:02d}/{ano}",
                ano=ano,
                mes=mes,
                fatura=fatura,
                consumo_kwh=kwh,
            )
        )
    return result


def parse_faturas(html: str) -> tuple[list[Fatura], Decimal | None]:
    """Parse the ``consultaDebitos.jsf`` table into invoices + total owed."""
    soup = BeautifulSoup(html, "html.parser")
    headers, rows = _find_datatable(soup, ["referência", "vencimento"])
    i_ref = _col(headers, "refer")
    i_num = _col(headers, "fatura")
    i_sit = _col(headers, "situa")
    i_orig = _col(headers, "origem")
    i_venc = _col(headers, "vencimento")
    i_atraso = _col(headers, "atraso")
    i_valor = _col(headers, "valor")

    def cell(row: list[str], index: int | None) -> str:
        if index is None or index >= len(row):
            return ""
        return row[index]

    faturas: list[Fatura] = []
    total = Decimal(0)
    seen_valor = False
    for row in rows:
        ref = _clean(cell(row, i_ref))
        if _parse_referencia(ref) is None:
            continue
        valor = _parse_valor(cell(row, i_valor))
        if valor is not None:
            total += valor
            seen_valor = True
        faturas.append(
            Fatura(
                referencia=ref,
                numero=_text_or_none(cell(row, i_num)),
                situacao=_text_or_none(cell(row, i_sit)),
                origem=_text_or_none(cell(row, i_orig)),
                vencimento=_parse_data(cell(row, i_venc)),
                dias_atraso=_parse_int(cell(row, i_atraso)),
                valor=valor,
            )
        )
    return faturas, (total if seen_valor else None)


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Response:
    status: int
    html: str
    url: str


class CopelClient:
    """Scraping client for the Copel Agência Virtual."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        documento: str,
        senha: str,
        *,
        base_url: str = API_ORIGIN,
        timeout: float = API_TIMEOUT_SECONDS,
    ) -> None:
        """Initialize the client.

        ``documento`` is the CPF/CNPJ used to log in; ``senha`` the AVA password.
        """
        self._session = session
        self._documento = re.sub(r"\D", "", documento)
        self._senha = senha
        self._base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._logged_in = False
        self._login_lock = asyncio.Lock()

    @property
    def is_authenticated(self) -> bool:
        """Return True if a session has been established."""
        return self._logged_in

    def _url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        return f"{self._base_url}{path}"

    async def _get(self, path: str) -> _Response:
        try:
            async with self._session.get(
                self._url(path), headers=_HEADERS, timeout=self._timeout
            ) as response:
                return _Response(
                    response.status, await response.text(), str(response.url)
                )
        except TimeoutError as err:
            raise CopelConnectionError(f"Timeout on GET {path}") from err
        except aiohttp.ClientError as err:
            raise CopelConnectionError(f"Error on GET {path}: {err}") from err

    async def _post(self, path: str, data: dict[str, str]) -> _Response:
        headers = {**_HEADERS, "Origin": self._base_url, "Referer": self._url(path)}
        try:
            async with self._session.post(
                self._url(path), data=data, headers=headers, timeout=self._timeout
            ) as response:
                return _Response(
                    response.status, await response.text(), str(response.url)
                )
        except TimeoutError as err:
            raise CopelConnectionError(f"Timeout on POST {path}") from err
        except aiohttp.ClientError as err:
            raise CopelConnectionError(f"Error on POST {path}: {err}") from err

    # -- JSF form helpers ---------------------------------------------------

    @staticmethod
    def _login_form(html: str) -> tuple[str, dict[str, str], str, str]:
        """Locate the login form and return its POST components.

        Returns (action, hidden_fields, doc_field, password_field). JSF
        generates unstable ids (``j_idt*``), so the form is identified
        structurally: the one containing a password input. All hidden inputs
        (including ViewState) are collected so the POST mirrors the browser.
        """
        soup = BeautifulSoup(html, "html.parser")
        for form in soup.find_all("form"):
            password = form.find("input", attrs={"type": "password"})
            if not password or not password.get("name"):
                continue
            action = form.get("action") or _LOGIN_PATH
            hidden: dict[str, str] = {}
            doc_field: str | None = None
            for inp in form.find_all("input"):
                name = inp.get("name")
                if not name:
                    continue
                itype = (inp.get("type") or "text").lower()
                if itype == "hidden":
                    hidden[name] = inp.get("value", "")
                elif itype in ("text", "tel", "number") and doc_field is None:
                    doc_field = name
            # The form's own name and its submit button ("Entrar") are posted
            # back by JSF to trigger the login action.
            if form.get("id"):
                hidden.setdefault(form["id"], form["id"])
            for button in form.find_all("button"):
                if button.get("name"):
                    hidden[button["name"]] = button.get("value", "")
            for submit in form.find_all("input", attrs={"type": "submit"}):
                if submit.get("name"):
                    hidden[submit["name"]] = submit.get("value", "")
            if doc_field is None:
                raise CopelApiError("Login form has no document field")
            return action, hidden, doc_field, password["name"]
        raise CopelApiError("Could not find the login form")

    # -- high-level flow ----------------------------------------------------

    async def async_login(self) -> None:
        """Log in and land on the UC list page."""
        async with self._login_lock:
            await self._async_login()

    async def _async_login(self) -> None:
        self._logged_in = False
        page = await self._get(_LOGIN_PATH)
        if page.status >= 500:
            raise CopelConnectionError(f"Login page HTTP {page.status}")

        action, data, doc_field, pwd_field = self._login_form(page.html)
        data[doc_field] = self._documento
        data[pwd_field] = self._senha

        result = await self._post(action, data)
        if result.status in (401, 403):
            raise CopelAuthError(f"Login rejected (HTTP {result.status})")
        if result.status >= 500:
            raise CopelConnectionError(f"Login failed (HTTP {result.status})")

        # A successful login lands on the UC list; anything else (still on the
        # login page, an error banner) means the credentials were rejected.
        final_url = result.url.lower()
        if (
            "listarucs" in final_url
            or "tbUcs" in result.html
            or "Unidade consumidora" in result.html
        ):
            self._logged_in = True
            _LOGGER.debug("Logged in to the Copel AVA")
            return
        raise CopelAuthError("CPF/CNPJ ou senha inválidos")

    async def _ensure_login(self) -> None:
        if not self._logged_in:
            await self.async_login()

    async def async_list_ucs(self) -> list[CopelUc]:
        """Return the consumer units on the account."""
        await self._ensure_login()
        page = await self._get(_LIST_UCS_PATH)
        if page.status != 200:
            raise CopelApiError(f"UC list returned HTTP {page.status}")
        return parse_ucs(page.html)

    async def async_select_uc(self, uc: CopelUc) -> None:
        """Select ``uc`` so subsequent data pages return its data.

        Selecting a UC is a JSF command link on the UC table that stores the
        current UC in the server session and navigates to ``inicio.jsf``. We
        reproduce it as a plain (non-AJAX) form postback: the link's id posted
        as its own parameter triggers the action.
        """
        page = await self._get(_LIST_UCS_PATH)
        soup = BeautifulSoup(page.html, "html.parser")
        form = None
        for candidate in soup.find_all("form"):
            if candidate.find(id=re.compile(r"tbUcs")):
                form = candidate
                break
        if form is None:
            raise CopelApiError("UC table form not found")

        # The clickable "Selecionar" link of the target row (id ends :<row>:<gen>).
        link = soup.find("a", id=re.compile(rf":tbUcs:{uc.row_index}:")) or soup.find(
            "a", id=re.compile(r":tbUcs:\d+:")
        )
        if link is None or not link.get("id"):
            raise CopelApiError(f"Select link for UC row {uc.row_index} not found")

        data = {
            inp["name"]: inp.get("value", "")
            for inp in form.find_all("input", attrs={"name": True})
        }
        form_id = form.get("id", "")
        if form_id:
            data.setdefault(form_id, form_id)
        # Non-AJAX JSF postback: the command link posts its own id back.
        data[link["id"]] = link["id"]
        action = form.get("action") or _LIST_UCS_PATH
        result = await self._post(action, data)
        if "inicio" not in result.url.lower():
            _LOGGER.debug(
                "UC %s selection landed on %s (expected inicio.jsf)",
                uc.codigo,
                result.url,
            )

    async def async_get_consumo(self) -> list[ConsumoMes]:
        """Return monthly consumption for the currently selected UC.

        The page shows the 10 most recent months. Older months live on further
        paginator pages (a PrimeFaces AJAX call); fetching the full ~30-month
        history for the Energy Dashboard backfill is a planned enhancement.
        """
        page = await self._get(_CONSUMO_PATH)
        if page.status != 200:
            raise CopelApiError(f"Consumo page returned HTTP {page.status}")
        try:
            return parse_consumo(page.html)
        except CopelApiError:
            # No consumption table (e.g. a UC without Grupo B history).
            _LOGGER.debug("No consumption table for the selected UC")
            return []

    async def async_get_faturas(self) -> tuple[list[Fatura], Decimal | None]:
        """Return invoices and total owed for the currently selected UC."""
        page = await self._get(_DEBITOS_PATH)
        if page.status != 200:
            raise CopelApiError(f"Débitos page returned HTTP {page.status}")
        return parse_faturas(page.html)

    async def async_get_all_data(self) -> dict[str, CopelUcData]:
        """Log in and scrape consumption + invoices for every UC.

        Returns a dict keyed by UC code. Selection is stateful, so UCs are
        scraped sequentially.
        """
        await self.async_login()
        ucs = await self.async_list_ucs()
        if not ucs:
            raise CopelApiError("No consumer units returned for this account")

        data: dict[str, CopelUcData] = {}
        for uc in ucs:
            if len(ucs) > 1:
                await self.async_select_uc(uc)
            consumo = await self.async_get_consumo()
            faturas, total = await self.async_get_faturas()
            data[uc.codigo] = CopelUcData(
                uc=uc, consumo=consumo, faturas=faturas, total_debitos=total
            )
        return data

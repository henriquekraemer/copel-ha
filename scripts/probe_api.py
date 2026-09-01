"""Log in to the Copel Agência Virtual and dump consumption + invoices.

Useful for verifying the scraping client against a real account without running
Home Assistant, and for capturing HTML to build test fixtures. Personal data is
redacted in the printed summary.

    cp .env.example .env          # fill in COPEL_DOCUMENTO / COPEL_SENHA
    python3 scripts/probe_api.py
    python3 scripts/probe_api.py --dump-html captures/   # save raw pages (gitignored)

Environment variables override the .env file. Requires aiohttp + beautifulsoup4.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import os
import pathlib
import sys
import types

import aiohttp

ROOT = pathlib.Path(__file__).resolve().parent.parent
_PKG_DIR = ROOT / "custom_components" / "copel"


def _load_api() -> types.ModuleType:
    """Load api.py as a standalone module without running the HA __init__.

    The integration package's __init__.py imports Home Assistant, which is not
    available outside HA. We register a synthetic package so api.py's relative
    ``from .const import ...`` resolves, then exec only const.py and api.py.
    """
    pkg = types.ModuleType("_copel_standalone")
    pkg.__path__ = [str(_PKG_DIR)]
    sys.modules["_copel_standalone"] = pkg
    for name in ("const", "api"):
        spec = importlib.util.spec_from_file_location(
            f"_copel_standalone.{name}", _PKG_DIR / f"{name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"_copel_standalone.{name}"] = module
        spec.loader.exec_module(module)
    return sys.modules["_copel_standalone.api"]


CopelClient = _load_api().CopelClient

ENV_FILE = ROOT / ".env"


def load_credentials() -> tuple[str, str]:
    values: dict[str, str] = {}
    if ENV_FILE.exists():
        for raw_line in ENV_FILE.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip("'\"")
    documento = os.environ.get("COPEL_DOCUMENTO") or values.get("COPEL_DOCUMENTO")
    senha = os.environ.get("COPEL_SENHA") or values.get("COPEL_SENHA")
    if not documento or not senha:
        sys.exit(f"COPEL_DOCUMENTO and COPEL_SENHA not set (environment or {ENV_FILE})")
    return documento, senha


def mask(value: str | None) -> str:
    if not value:
        return "-"
    text = str(value)
    return text[:3] + "…" + text[-2:] if len(text) > 6 else "***"


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dump-html", metavar="DIR", help="save raw page HTML into DIR (gitignored)"
    )
    args = parser.parse_args()

    documento, senha = load_credentials()
    async with aiohttp.ClientSession() as session:
        client = CopelClient(session, documento, senha)
        await client.async_login()
        print("login ok")

        data = await client.async_get_all_data()
        print(f"{len(data)} consumer unit(s)\n")
        for codigo, uc_data in data.items():
            uc = uc_data.uc
            print(f"UC {mask(codigo)}  {uc.cidade}  grupo={uc.grupo} sit={uc.situacao}")
            atual = uc_data.consumo_atual
            if atual:
                print(f"  consumo atual: {atual.referencia} -> {atual.consumo_kwh} kWh")
            print(f"  meses de consumo: {len(uc_data.consumo)}")
            fatura = uc_data.fatura_atual
            if fatura:
                print(
                    f"  fatura atual: {fatura.referencia} venc={fatura.vencimento} "
                    f"valor=R$ {fatura.valor} sit={fatura.situacao} "
                    f"atraso={fatura.dias_atraso}"
                )
            print(f"  total débitos: R$ {uc_data.total_debitos}\n")

        if args.dump_html:
            out = pathlib.Path(args.dump_html)
            out.mkdir(parents=True, exist_ok=True)
            for name, path in (
                ("listar_ucs", "/paginas/listarUcsDoc.jsf"),
                ("consumo", "/paginas/historicoConsumoGrupoB.jsf"),
                ("debitos", "/paginas/consultaDebitos.jsf"),
            ):
                page = await client._get(path)
                (out / f"{name}.local.html").write_text(page.html, encoding="utf-8")
            print(f"raw HTML saved to {out}/ (remember: contains personal data)")


if __name__ == "__main__":
    asyncio.run(main())

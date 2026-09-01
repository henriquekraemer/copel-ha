# Changelog

## [Unreleased]

### Added
- Initial project skeleton for the Copel ↔ Home Assistant integration.
- Scraping client (`api.py`) for the Copel Agência Virtual (AVA), a JSF/PrimeFaces
  portal with no JSON API: session login, UC listing, consumption history and
  invoices/debts, parsed from server-rendered HTML tables.
- Config flow (CPF/CNPJ + password) with reauth, reconfigure and options
  (scan interval).
- Sensors per consumer unit: current/previous month consumption (kWh), invoice
  amount, due date, total owed, days overdue.
- Binary sensor: invoice overdue.
- Diagnostics with redaction of personal data.
- `scripts/probe_api.py` to exercise the client against a real account.

### Verified live (2026-08-31)
- JSF login flow (form `formulario`, fields `numDoc`/`pass`, dynamic submit button)
  against a real account.
- Multi-UC selection (non-AJAX JSF postback) correctly switches the active UC.
- Consumption (kWh) and invoice parsing against real data.

### Known gaps
- Consumption history is limited to the months on the first page; fetching the full
  history needs the PrimeFaces AJAX paginator (returns XML partial-response).
- Energy Dashboard historical statistics backfill.
- Copel rate-limits rapid logins; the integration logs in once per refresh (6 h default).

### Outage feature — deferred
Real-time outage (`falta de energia`) is not shipped. Copel's public/no-login outage
services are reCAPTCHA-gated (see `docs/recon-ava-web.md`). The viable source is the
**mobile app's authenticated JSON API** (`com.copel.mbf`), which exposes power-outage
status by UC — its endpoint map is documented in `docs/recon-mobile-api.md`; only the
authentication (Firebase Remote Config `x-api-key` + login handshake) remains to be
captured. That API would also unlock daily consumption and cleaner data overall.

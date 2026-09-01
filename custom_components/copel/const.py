"""Constants for the Copel integration."""

from typing import Final

DOMAIN: Final = "copel"
MANUFACTURER: Final = "Copel"

# The Agência Virtual de Atendimento (AVA) — a JSF/PrimeFaces app. Paths in the
# client are site-absolute (start with /avaweb) because JSF form actions are, so
# the HTTP base is the bare origin.
API_ORIGIN: Final = "https://www.copel.com"
API_BASE_URL: Final = f"{API_ORIGIN}/avaweb"  # user-facing link (configuration_url)
API_TIMEOUT_SECONDS: Final = 30

# Config entry keys. Login is by CPF/CNPJ + password (the "documento").
CONF_DOCUMENTO: Final = "documento"

# The monthly billing/consumption data changes at most once a month, so a slow
# poll is plenty. Expressed in seconds and exposed through the options flow.
DEFAULT_SCAN_INTERVAL: Final = 6 * 60 * 60  # 6 hours
MIN_SCAN_INTERVAL: Final = 30 * 60  # 30 minutes
MAX_SCAN_INTERVAL: Final = 24 * 60 * 60  # 24 hours

# How many months of consumption history to request from the AVA (page size on
# the PrimeFaces DataTable; the portal offers 10/20/30).
CONSUMO_PAGE_SIZE: Final = 30

ATTR_UC_ANEEL: Final = "uc_aneel"
ATTR_UC_ANTIGA: Final = "uc_antiga"
ATTR_CIDADE: Final = "cidade"
ATTR_ENDERECO: Final = "endereco"
ATTR_GRUPO: Final = "grupo"
ATTR_SITUACAO: Final = "situacao"
ATTR_REFERENCIA: Final = "referencia"
ATTR_NUMERO_FATURA: Final = "numero_fatura"
ATTR_ORIGEM: Final = "origem"
ATTR_DIAS_ATRASO: Final = "dias_atraso"

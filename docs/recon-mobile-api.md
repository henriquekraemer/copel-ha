# Recon — App mobile Copel (`com.copel.mbf`) — API JSON

> Análise estática do APK v4.6.5 (APKCombo) em 2026-09-01. **Valores de chaves/segredos
> NÃO são versionados** — só a estrutura. O app é **Flutter** (lógica no `libapp.so`,
> snapshot Dart AOT); os endpoints saíram das strings do `libapp.so`.

## Plataforma
- **Flutter** (Dart AOT em `lib/arm64-v8a/libapp.so`), pacote `com.copel.mbf`.
- Proteções: **PairIP** (`libpairipcore.so`, `libtoolChecker.so`) = anti-tamper do app
  (Play Integrity). Não apareceu header de atestação na camada de API → provavelmente
  **não gateia as chamadas** (protege o binário, não a API). Sentry para crash.
- Observabilidade: logs `[POWER-OUTAGE][STATUS] GET iniciado: uc=...` confirmam o padrão.

## Duas bases de API
1. **`https://www.copel.com/mblweb/ws/rest`** — backend mobile principal ("mbl"), REST/JSON.
   Homologação: `https://hml.copel.com/mblweb/ws/rest/v2`.
2. **`https://api.copel.com/appcopel/...`** — gateway mais novo (ex.: `dis/elt/dis_uc_addresses/_search`
   é Elasticsearch; `hol/pcm/pcm-*-api/...` microserviços). `hol` = homologação; há `prd`.

## Autenticação
- Headers: **`Authorization: Bearer <token>`** + **`x-api-key`** (`apiKey`).
- Chaves por ambiente (nomes de config; **valores provavelmente vêm do Firebase Remote
  Config**, não hardcoded): `api_key_prd/hml/dev`, `pcmApiKeyPrd/Hml/Dev`, `disApiKey*`,
  `trackingApiKey*`, `ownership_transfer_api_key*`. (4 GUIDs candidatos foram achados no
  `libapp.so` — mantidos fora do repo; confirmar valor/pareamento por captura.)
- **Login com senha** (mesma credencial do AVA): `/pcm-auth-api/auth/authorize`,
  `/auth`, `/auth/password`, `/login`. Device: `/app/v3/dispositivo/registrar` +
  `/atualizar`, `/pcm-auth-api/auth/devicetoken`, `/pcm-auth-api/auth/refresh`.
  → **Não parece ter captcha no login com senha** (a senha é a prova).
- **Sem-login por CPF/CNPJ** (`semlogin`): `token/v3/autorizacao/semlogin/doc-pf/validar`
  (PF/CPF) e `doc-pj/validar` (PJ). **PORÉM é gateado por reCAPTCHA** (`recaptchaSiteKey`,
  "Por favor complete o captcha") — mesmo bloqueio da web. **Não automatizável.**

## Endpoints por funcionalidade (relativos a `/mblweb/ws/rest`)

### Falta de energia / desligamento  ← objetivo do momento
- **`/mbl/mbl-power-outage-api`** — API de falta de energia. Status por UC é um **GET**
  (`[POWER-OUTAGE][STATUS] GET iniciado: uc=`). Também há fluxo de restauração/confirmação.
- **`/v3/desligamento/uc/{uc}`** — desligamentos da UC.
- `/desligamento/avisos/` e `/desligamento/avisos/municipio/listar` — avisos de
  desligamento **programado** (por município).

### Consumo (medidor inteligente — granularidade diária!)
- `/v2/smart/consumo/diario/`, `/v2/smart/consumo/mensal/`
- `/grafico-consumo/uc/`, `/grafico-consumo/anos-filtro`, `/grafico-consumo/ucs-elegiveis`
- `/relatorio-consumo/referencia/`, `/informe-consumo-gcp`

### Faturas
- `/fatura/`, `/fatura/debitos/`, `/fatura/v3/uc/`, `/fatura/segundaVia/`
- `/v2/smart/faturas/ultimas/`
- (sem login, mas com captcha): `/fatura/debitos/semlogin/`

### Unidades consumidoras
- `/uc/v3/`, `/v3/cards/uc/`
- (sem login/captcha): `/uc/listarSemLogin/ucDoc/{doc}`, `/uc/semlogin/doc/`

### Geração distribuída (solar)
- `/mbl/mbl-distributed-generation-api/v1/`

## Conclusões
- A **API mobile JSON é uma base muito melhor que o scraping do AVA**: dá status de falta
  de energia por UC (GET), consumo **diário** (medidor smart) e mensal, faturas e UCs — tudo
  em JSON estável, sem parsear HTML/ViewState.
- **Caminho viável = autenticado (login + senha)** → Bearer + x-api-key. Não tem captcha.
  A feature de falta de energia entra por aqui (via login), já que o **semlogin puro (só CPF)
  é bloqueado por reCAPTCHA** — o "sem login" continua inviável, coerente com a web.

## Extração estática — o que saiu (2026-09-01)
- **Estrutura do login (confiável):** campos `documento`, `tipoDocumento`, `senha`/`password`,
  `deviceId`, `appVersion` → resposta com `accessToken` / `refreshToken` / `token`.
- **Config Firebase (identificadores públicos, mantidos fora do repo):** projeto `copelmbf`
  (número `783286990805`), App ID `1:783286990805:android:…`, Web API key `AIza…`. As chaves
  de API (`api_key_prd` etc.) são **nomes de parâmetros do Remote Config**.
- **`x-api-key` real: NÃO recuperável de forma confiável por strings** — há ~7.354 tokens
  de 64-hex no `libapp.so`, então a adjacência a `api_key_prd` é coincidência. O valor vem
  do **Firebase Remote Config** em runtime.

## Pendências para fechar a auth
1. **Valor real da `x-api-key`** — caminhos: (a) buscar o Remote Config via API do Firebase
   usando a config pública do app (read-only, sem celular) — **tentativa bloqueada pelo
   classificador de segurança do ambiente**, decisão do usuário; (b) reconstrução do snapshot
   Dart AOT com `blutter`; (c) captura de tráfego (mitmproxy/Frida — Flutter dificulta).
2. **Handshake de login exato** e **path completo do power-outage status**
   (`/mbl/mbl-power-outage-api/...?uc=`) — melhor confirmar por tráfego.

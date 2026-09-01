# Recon — Copel Agência Virtual (AVA web) — Fase 0

> Notas de engenharia reversa da fonte de dados para a integração Copel ↔ Home Assistant.
> Dados pessoais (nome, UC real, endereço, nº de fatura, valores) **redigidos** — só a
> estrutura interessa. Captura feita em 2026-08-31 via navegador, sessão autenticada do titular.

## Plataforma

- Portal: **AVA — Agência Virtual de Atendimento v4.2.1**.
- Base URL: `https://www.copel.com/avaweb/`
- Stack: **JavaServer Faces (JSF) + PrimeFaces 5.3**, tema `primefaces-spark-orange`.
- **Não há API REST/JSON.** As páginas são **HTML renderizado no servidor** (full-page
  navigation via GET/POST). Componentes de dados são **PrimeFaces DataTable** (tabela HTML).
- Sessão baseada em **cookie** (JSESSIONID). A UC "logada" é guardada no estado da sessão
  no servidor — depois de selecionar uma UC, as páginas de dados abrem por **GET** e já
  retornam os dados daquela UC.

### Implicação para o cliente
O `api.py` **não** consome JSON — ele faz **scraping de HTML**:
1. `aiohttp.ClientSession` com cookie jar (mantém JSESSIONID).
2. Login (POST com `javax.faces.ViewState`).
3. Selecionar UC (POST na DataTable, com ViewState) — define a UC na sessão.
4. GET nas páginas de dados → parsear as tabelas com `lxml`/`BeautifulSoup`.
Parsing de HTML é mais frágil que JSON; por isso o cliente fica **isolado** em `api.py`
(camada 1), como no `udiconnect-plus-ha`, com dataclasses tipadas e testes sobre HTML fixado.

## Fluxo de autenticação — ✅ VERIFICADO (2026-08-31)

1. Home `https://www.copel.com` → botão **Login** → `avaweb/paginaLogin/login.jsf`.
2. Login por **CPF/CNPJ + senha** (ou "Acessar utilizando a Unidade Consumidora").
   - **Sem 2FA/OTP nem captcha** no login web (confirmado).
   - Há fluxo de "Esqueceu a senha / primeiro acesso" que envia **senha provisória por
     e-mail/SMS** e exige "Ativar meu cadastro" (evitar acionar por engano).
3. Pós-login → `avaweb/paginas/listarUcsDoc.jsf` (**lista de UCs**).
4. "Selecionar" numa UC → `avaweb/paginas/inicio.jsf` (home da UC).
5. "Trocar de unidade consumidora" volta para `listarUcsDoc.jsf` (troca a UC da sessão).

### Detalhes do POST de login (verificados)
- Formulário `id=formulario`, `method=post`. A `action` inclui `;jsessionid=...`
  (JSF path-encoded) — use a `action` do HTML verbatim.
- Campos: `formulario:numDoc` (CPF/CNPJ), `formulario:pass` (senha),
  hidden `formulario` (id do form) e `javax.faces.ViewState`.
- Botão submit **não-ajax** `formulario:j_idt41` (rótulo "Entrar") — o `j_idt*` é gerado,
  então o cliente extrai o botão dinamicamente e envia `nome=valor`.
- Sucesso = resposta cai em `listarUcsDoc.jsf` (a `_async_login` detecta por URL/UC table).

### Seleção de UC (verificada)
- A DataTable `formLogin:tbUcs` tem um link "Selecionar" por linha, com id
  `formLogin:tbUcs:<row>:<gen>` (o `<gen>` é igual entre as linhas; só o `<row>` muda).
- Selecionar = **postback JSF não-ajax**: enviar os campos do form `formLogin` (+ ViewState)
  e o id do link como parâmetro próprio (`{linkId: linkId}`). Redireciona para `inicio.jsf`
  e fixa a UC na sessão. Confirmado que troca corretamente entre as UCs.
- **Não** usar os parâmetros `javax.faces.partial.ajax` — a resposta AJAX é XML partial
  e além de não trazer a tabela, atrapalha o estado da sessão.

### ⚠️ Rate-limiting / anti-bot
Vários logins em sequência rápida (~6 em poucos minutos) passaram a ser rejeitados
(a página deixa de cair em `listarUcsDoc`). Em produção o poll é 1×/6h, então não é
problema; mas em testes, espaçar os logins. O `probe_api.py` deve ser usado com parcimônia.

## Multi-UC

- `listarUcsDoc.jsf` lista todas as UCs do titular. Colunas:
  `Unidade consumidora ANEEL` (12 díg.) · `Unidade consumidora antiga` · `Cidade` ·
  `Endereço` · `Grupo` (ex.: B) · `Situação` (ex.: LG) · `Selecionar`.
- A seleção é **stateful** (server-side). Para raspar N UCs: selecionar UC → raspar →
  trocar UC → raspar (sequencial, não paralelo na mesma sessão).

## Endpoints de dados (todos em `avaweb/paginas/`)

| Serviço | Página `.jsf` | Uso na integração |
|---|---|---|
| Lista de UCs | `listarUcsDoc.jsf` | descobrir UCs (device por UC) |
| Home da UC | `inicio.jsf` | contexto/seleção |
| **Histórico de consumo** | `historicoConsumoGrupoB.jsf` | **sensor kWh + Energy Dashboard** |
| **Consulta de débitos / 2ª via** | `consultaDebitos.jsf` | **sensores de fatura (valor, vencimento, status)** |
| Histórico de pagamento | `historicoPagamento.jsf` | (opcional) pagamentos |
| Emitir 2ª via | `segundaViaFatura.jsf` | (opcional) link p/ boleto |
| Fatura digital | `faturaDigital.jsf` | — |
| Micro/mini geração | `demonstrativoMicroMiniGeracao.jsf` | (futuro) solar |
| Religação | `religacaoInterno.jsf` | — (ação, fora de escopo) |

> `historicoConsumoGrupoB` = **Grupo B (residencial)**. Grupo A teria página distinta;
> as UCs do titular são ambas Grupo B.

### `historicoConsumoGrupoB.jsf` — schema
DataTable paginada (~30 meses; 3 páginas × 10; seletor de tamanho de página; export Excel):

| Coluna | Formato | Exemplo (redigido) |
|---|---|---|
| Mês de referência | `MM/AAAA` | `MM/AAAA` |
| Fatura | nº fatura (14 díg.) | `<redigido>` |
| Consumo kWh | inteiro | `NNN` |

- Ordenado do mês mais recente para o mais antigo.
- Para o Energy Dashboard: ler todas as páginas (ou aumentar page size) e injetar
  estatísticas mensais via `async_add_external_statistics`.

### `consultaDebitos.jsf` — schema ("Débitos da UC Logada")
| Coluna | Formato |
|---|---|
| Mês de referência | `MM/AAAA` |
| Nr. da fatura | 14 díg. |
| Situação da fatura | ex.: `AB` (aberta) |
| Origem | ex.: `FATURAMENTO NORMAL` |
| Data de vencimento | `DD/MM/AAAA` |
| Dias em atraso | inteiro (vazio se em dia) |
| Valor emitido (R$) | decimal `1.234,56` |
| Via / Via cartão | links de pagamento |

Rodapé: `Total de débitos da unidade consumidora: <R$>`.
→ Sensores: valor da fatura atual, vencimento, situação, dias em atraso, total em aberto.

## Falta de energia / manutenção — recon feito (2026-08-31): **bloqueado por reCAPTCHA**

Os serviços públicos (sem login) de falta de energia da Copel **não são automatizáveis**:

1. **"Sem Luz"** — `https://www.copel.com/slwweb/publico/semluz/inicio.jsf` (embutido em
   `/site/copel-distribuicao/falta-de-luz/`). App JSF/PrimeFaces 7. É um fluxo de
   **registro de ocorrência**, não uma consulta de status: informar UC/CPF/CNPJ/NIO →
   *"Toda a vizinhança está sem luz?"* → *"Confirma solicitação?"* → gera protocolo. Ou seja,
   automatizar arriscaria **abrir protocolos falsos**, e o passo final tem **reCAPTCHA**.
2. **"Desligamentos Programados"** — `https://www.copel.com/desligamentos/` (form → `index.jsp`).
   Consulta por número da UC, read-only, mostra "Dados atualizados em ...". **Mas exige
   reCAPTCHA** ("Não sou um robô") na própria consulta.

Como não se pode burlar CAPTCHA (e ele bloquearia o cliente), **não há fonte pública sem
login viável** para o `binary_sensor` de falta de energia.

Observação de formato: a UC "nova" ANEEL tem **15 dígitos**; a `UC ANEEL` do AVA
(`listarUcsDoc`) veio com **12** — checar o mapeamento antes de usar a UC nesses serviços.

### Caminhos que sobram para a feature de falta de energia
- **API do app mobile** (`com.copel.mbf`) — autenticada, provavelmente REST/JSON com status
  de falta de luz por UC **sem captcha**. Melhor fonte, mas exige recon do APK/mitmproxy e
  **usa login**. (Fora do "sem login".)
- **Detecção local no HA** (sem Copel) — UPS, ping a um dispositivo da casa, ou energia do
  host do HA. Tempo real e confiável, mas só funciona se o HA sobreviver à queda (UPS/off-site).
- **Adiar** a feature e manter a integração de consumo/fatura (que funciona).

## Riscos / notas
- **Fragilidade de scraping:** mudanças de layout quebram o parser → isolar em `api.py`,
  testar com HTML fixado, `diagnostics` com redação.
- **ViewState:** necessário para POSTs (login, seleção de UC). Extrair do HTML da página
  anterior a cada POST.
- **Cadência:** consumo/fatura mudam no máximo 1×/mês → poll 1×/dia. Falta de energia
  (quando mapeada) → poll mais frequente.
- **Alternativa (fallback):** o app mobile `com.copel.mbf` provavelmente usa API REST/JSON
  mais estável. Se o scraping do AVA se mostrar frágil demais, reconsiderar decompilar o
  APK / interceptar o app. Fora do escopo escolhido (web) por ora.

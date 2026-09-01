# Copel para Home Assistant

Integração não oficial que traz os dados da sua conta de luz da Copel para o
Home Assistant: consumo mensal, valor e vencimento da fatura e débitos em aberto,
com uma unidade consumidora por device.

Não tem vínculo nenhum com a Copel. Como não existe API pública, ela lê os dados
da Agência Virtual (o mesmo portal que você acessa no navegador) usando o seu
login. Se a Copel mexer no portal, pode quebrar. É o preço de não ter API oficial.

## O que aparece no Home Assistant

Para cada unidade consumidora:

- Consumo do mês e do mês anterior (kWh)
- Valor e vencimento da fatura atual
- Total de débitos em aberto
- Dias em atraso, e um `binary_sensor` de "fatura em atraso"

Se você tem mais de uma UC na mesma conta, todas aparecem.

## Instalação

Pelo HACS, como repositório personalizado:

1. HACS → Integrações → menu (⋮) → Repositórios personalizados
2. Adicione `https://github.com/henriquekraemer/copel-ha` na categoria *Integration*
3. Instale e reinicie o Home Assistant
4. Configurações → Dispositivos e serviços → Adicionar integração → Copel
5. Entre com o CPF/CNPJ e a senha da Agência Virtual

Os dados da Copel são mensais, então a integração consulta o portal a cada 6 horas
por padrão. Dá pra mudar isso nas opções da integração.

## Como funciona por baixo

A Agência Virtual é um app JSF/PrimeFaces que devolve HTML, não JSON. A integração
mantém a sessão logada, seleciona a UC e lê as tabelas de histórico de consumo e de
débitos, virando sensores. Toda a parte frágil (o parsing do HTML) fica isolada em
`api.py` — quando a Copel mudar o layout, é ali que se conserta. As anotações do que
foi mapeado no portal estão em [`docs/recon-ava-web.md`](docs/recon-ava-web.md).

## Desenvolvimento

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements_dev.txt
ruff check . && ruff format --check .
pytest
```

Para testar contra uma conta de verdade sem subir o Home Assistant, use o
`scripts/probe_api.py`: copie `.env.example` para `.env`, preencha as credenciais
(o `.env` está no `.gitignore`) e rode. Ele faz login, lista as UCs e imprime o
consumo e as faturas.

## Licença

MIT.

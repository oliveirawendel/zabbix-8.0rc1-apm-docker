# Zabbix 8.0 RC1 com APM: laboratório de estudo de comportamento

Laboratório completo para estudar o comportamento do **APM com OpenTelemetry** no **Zabbix 8.0.0rc1**, com um proxy compilado com `--with-apm`, um gateway OpenTelemetry e uma aplicação de exemplo com três serviços, banco de dados, carga contínua e erros provocados de propósito.

> ⚠️ **Laboratório, não produção.** Senhas simples, portas abertas no host e sem TLS. Use somente em uma máquina de teste.

## Versões testadas

| Componente | Origem |
|---|---|
| Zabbix (server, web, agente 2) | `zabbix/*:alpine-trunk` (imagens oficiais) |
| Zabbix proxy com APM | código-fonte da tag `8.0.0rc1` (revisão `dd0d9c2`), definida em `proxy/.env` |
| Templates e entrypoint do proxy | branch `trunk` do `zabbix-docker` (`ARG ZBX_DOCKER_REF` em `proxy/Dockerfile`) |
| TimescaleDB | `timescale/timescaledb:2.29.2-pg18` |
| ClickHouse | `clickhouse/clickhouse-server:26.4` |
| OpenTelemetry Collector | `otel/opentelemetry-collector-contrib:0.161.0` |
| Aplicação de estudo | `python:3.12-slim` + `postgres:16-alpine` |

> **Atenção:** não use `ZBX_REF=master` no `proxy/.env`. A branch `master` avança e já produziu binários sem as opções APM (`StartAPMCollectors`). Use sempre a tag `8.0.0rc1`.

## Arquitetura

```
 shop-api:8000  ─┐
 shop-users     ─┼──(OTLP/gRPC)──▶ ┌──────────────────────────┐  14317  ┌─────────────────┐       ┌────────────┐
 shop-orders    ─┘                 │ otel-gateway (4317)      │ ──────▶ │ zabbix-proxy    │ ────▶ │ ClickHouse │
                                   │ memory_limiter           │         │ (APM, 14317)    │       │ otel_*     │
                                   │ tail_sampling (10s)      │         └─────────────────┘       └────────────┘
                                   │ batch                    │                                        ▲
                                   └──────────────────────────┘         Zabbix server + frontend ──────┘
                                                                        (APM > Traces, Telemetry query)
```

**Fluxo de dados:** as aplicações enviam traces, logs e métricas por OTLP/gRPC para o **gateway**. O gateway agrupa os spans por `TraceId` durante 10 segundos (`tail_sampling`), faz batch e controle de memória, e envia para o **proxy do Zabbix**, que grava no **ClickHouse**. A interface do Zabbix lê os traces do ClickHouse, e os itens *Telemetry query* leem do PostgreSQL.

## Componentes

| Pasta | O que sobe | Portas no host |
|---|---|---|
| `/` (raiz) | Zabbix server, frontend (web), agente 2, PostgreSQL 18 + TimescaleDB, ClickHouse | Frontend `8080`, server `10051`, ClickHouse `8123` e `9000` |
| `proxy/` | Zabbix proxy 8.0.0rc1 compilado com APM (SQLite3) | `14317` (OTLP/gRPC) |
| `gateway/` | OpenTelemetry Collector (contrib) | `4317` (OTLP/gRPC) |
| `shop/` | PostgreSQL 16, `shop-users`, `shop-orders`, `shop-api` e `shop-loadgen` | API `8000` |

## Pré-requisitos

- Docker com Docker Compose (`docker compose version`)
- Git
- Cerca de 4 GB de RAM livres
- Cerca de 10 GB de disco livres em `/var` (o build do proxy compila o Zabbix e usa espaço temporário)

## Estrutura

```
docker-compose.yml        Zabbix server, web, agente, PostgreSQL + TimescaleDB, ClickHouse
.env                      versões e senhas da stack principal
clickhouse-init/          cria as tabelas otel_traces, otel_logs e otel_metrics_* na primeira subida
proxy/                    proxy com APM (Dockerfile, zabbix_proxy_apm.conf, compose.yaml, .env)
gateway/                  OpenTelemetry Collector (otel-gateway.yaml, compose.yaml)
shop/                     aplicação de estudo (api, users, orders, loadgen, banco, overrides)
```

## Ordem de subida

A ordem importa. As pastas `proxy/`, `gateway/` e `shop/` usam a rede `zabbix8_zbx`, criada pela stack da raiz. Suba sempre nesta sequência:

1. **Raiz** (cria a rede `zabbix8_zbx`)
2. **proxy/** (espera o ClickHouse e o server)
3. **gateway/**
4. **shop/**

## Passo a passo

### 1. Clone o repositório

```bash
git clone https://github.com/oliveirawendel/zabbix-8.0rc1-apm-docker.git
cd zabbix-8.0rc1-apm-docker
```

### 2. Senhas (opcional)

Os arquivos `.env` (raiz) e `proxy/.env` já vêm com senhas de laboratório (`trocar_senha`), então dá para subir sem alterar nada.

Para usar outras senhas, edite os dois arquivos **antes de subir**. A senha do ClickHouse precisa ser a mesma que você configurar depois no data source APM do frontend.

Confira também que `proxy/.env` define `ZBX_REF=8.0.0rc1`:

```bash
grep ZBX_REF proxy/.env
```

### 3. Suba a stack principal

```bash
docker compose up -d
docker compose ps
```

Aguarde os healthchecks de `postgres` e `clickhouse` ficarem `healthy` (até um minuto na primeira vez).

Confira os bancos:

```bash
source .env
docker compose exec postgres psql -U zabbix -d zabbix -c "SELECT extname, extversion FROM pg_extension WHERE extname='timescaledb'"
docker compose exec clickhouse clickhouse-client --user zabbix --password "$CLICKHOUSE_PASSWORD" -q "SHOW TABLES FROM zabbix"
```

Resultado esperado: `timescaledb 2.29.x` e sete tabelas no ClickHouse: `otel_traces`, `otel_logs` e `otel_metrics_*` (gauge, sum, histogram, exponential_histogram, summary).

### 4. Configure o frontend

Acesse `http://IP_DO_HOST:8080` com `Admin` / `zabbix`. **Troque a senha no primeiro acesso.**

- **Host "Zabbix server":** na interface do agente, use *Connect to: DNS*, `zabbix-agent`, porta `10050`.
- **Administration → Data sources → APM:** marque *Enable global data source* e preencha:
  - URL: `http://clickhouse:8123`
  - Usuário: `zabbix`
  - Senha: a `CLICKHOUSE_PASSWORD` (`trocar_senha` se você não alterou)
  - Database: `zabbix`

  Clique em *Update* e depois em *Test*. O teste precisa ser bem-sucedido.
- **Administration → Proxies → Create proxy:** nome `proxy-apm-01`, modo *Active*, e na aba *APM* marque *Data collection enabled*. Salve.

> **Importante:** sem o data source global e a opção *Data collection enabled* no proxy, o coletor APM não abre a porta `14317`. O proxy fica no log com `waiting for global APM data source configuration`.

> Os nomes dos campos seguem a interface da versão 8.0 RC1 e podem mudar em versões futuras.

### 5. Suba o proxy com APM

```bash
cd proxy
docker compose up -d --build
docker compose logs -f zabbix-proxy
```

A compilação leva vários minutos. Quando o proxy iniciar, o log deve conter:

- `Starting Zabbix Proxy (active) [proxy-apm-01]. Zabbix 8.0.0rc1`
- `APM support: YES`
- `Open Telemetry collector listening on 0.0.0.0:14317`

Não deve aparecer `unknown parameter` nem `does not match Zabbix database`. Em *Administration → Proxies*, o campo *Last seen* do `proxy-apm-01` deve atualizar.

Confirme a porta:

```bash
docker compose exec zabbix-proxy sh -c "netstat -ltn 2>/dev/null || cat /proc/net/tcp" | grep 14317
```

### 6. Suba o gateway

```bash
cd ../gateway
docker compose up -d
docker compose logs --tail=20 otel-gateway
```

O gateway escuta OTLP/gRPC em `4317`, agrupa os traces por 10 segundos e envia para `zabbix-proxy:14317`. Não deve aparecer `connection refused` depois que o proxy estiver no ar.

### 7. Suba a aplicação de estudo (`shop/`)

```bash
cd ../shop
docker compose up -d --build
docker compose ps
```

Os cinco serviços sobem com este compose. O `compose.override.yaml` é aplicado automaticamente e liga métricas e logs nos serviços certos.

| Serviço | Função | Porta |
|---|---|---|
| `shop-db` | PostgreSQL 16 com dados de exemplo (`db/init.sql`) | interna |
| `shop-users` | CRUD de usuários, endpoint lento e endpoint com erro | interna `5001` |
| `shop-orders` | CRUD de pedidos; chama `shop-users` ao criar pedido | interna `5002` |
| `shop-api` | Fachada pública; encaminha para users e orders e faz o *fan-out* de `/api/summary` | `8000` |
| `shop-loadgen` | Gera tráfego contínuo contra a API | nenhuma |

Teste a API:

```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8000/api/users
curl -s http://localhost:8000/api/summary/1
```

> Respostas `502 upstream unavailable` logo após a subida são normais: o `shop-api` pode iniciar antes do `shop-users` e do `shop-orders` estarem prontos. Os próximos requests devem funcionar.

### 8. Valide os traces

Espere cerca de 15 segundos (o gateway segura os traces por 10 segundos) e depois abra **APM → Traces** no frontend.

## Latência de visibilidade

O gateway usa `tail_sampling` com `decision_wait: 10s`: ele segura os spans de cada trace por 10 segundos antes de enviar ao proxy. Isso garante que o span raiz (`shop-loadgen`) chegue junto com os filhos, e os traces aparecem completos no Zabbix.

## Referências

- [Release notes do Zabbix 8.0.0rc1](https://www.zabbix.com/rn/rn8.0.0rc1)
- [Documentação do Zabbix 8.0: parâmetros do proxy](https://www.zabbix.com/documentation/8.0/en/manual/appendix/config/zabbix_proxy)
- [OpenTelemetry Collector: tail_sampling](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/tailsamplingprocessor)

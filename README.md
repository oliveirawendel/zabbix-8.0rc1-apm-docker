# Zabbix 8.0 RC1 com APM: laboratório de estudo de comportamento

Laboratório completo para estudar o comportamento do **APM com OpenTelemetry** no **Zabbix 8.0 RC1**, com um proxy compilado com `--with-apm`, um gateway OpenTelemetry e uma aplicação de exemplo com três serviços, banco de dados, carga contínua e erros provocados de propósito.

> ⚠️ **Laboratório, não produção.** Senhas simples, portas abertas no host e sem TLS. Use somente em uma máquina de teste.

## Arquitetura

```
 shop-api:8000  ─┐
 shop-users     ─┼──(OTLP/gRPC)──▶ ┌──────────────┐  14317  ┌─────────────────┐       ┌────────────┐
 shop-orders    ─┘                 │ otel-gateway │ ──────▶ │ zabbix-proxy    │ ────▶ │ ClickHouse │
                                   │ (4317)       │         │ (APM, 14317)    │       │ otel_*     │
                                   └──────────────┘         └─────────────────┘       └────────────┘
                                                                                             ▲
                                                            Zabbix server + frontend ────────┘
                                                            (APM > Traces, Telemetry query)
```

Fluxo de dados: as aplicações enviam traces, logs e métricas por OTLP/gRPC para o **gateway**. O gateway faz batch e controle de memória e envia para o **proxy do Zabbix**, que grava no **ClickHouse**. A interface do Zabbix lê os traces do ClickHouse, e os itens *Telemetry query* leem do PostgreSQL.

## Componentes

| Pasta | O que sobe | Portas no host |
|---|---|---|
| `/` (raiz) | Zabbix server, frontend (web), agente 2, PostgreSQL 18 + TimescaleDB, ClickHouse | Frontend `8080`, server `10051`, ClickHouse `8123` e `9000` |
| `proxy/` | Zabbix proxy compilado com APM (SQLite3) | `14317` (OTLP/gRPC) |
| `gateway/` | OpenTelemetry Collector (contrib) | `4317` (OTLP/gRPC) |
| `shop/` | PostgreSQL 16, `shop-users`, `shop-orders`, `shop-api` e `shop-loadgen` | API `8000` |

## Pré-requisitos

- Docker com Docker Compose v2 (`docker compose version`)
- Git
- Cerca de 4 GB de RAM livres e alguns minutos para compilar o proxy

## Estrutura

```
docker-compose.yml        Zabbix server, web, agente, PostgreSQL + TimescaleDB, ClickHouse
.env                      versões e senhas da stack principal
clickhouse-init/          cria as tabelas otel_traces, otel_logs e otel_metrics_* na primeira subida
proxy/                    proxy com APM (Dockerfile, conf, compose, .env)
gateway/                  OpenTelemetry Collector (otel-gateway.yaml, compose)
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
git clone https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git
cd SEU_REPOSITORIO
```

### 2. Troque as senhas

Edite `.env` (raiz) e `proxy/.env`. As duas senhas do ClickHouse precisam ser iguais.

```bash
# .env (raiz)
POSTGRES_PASSWORD=troque-esta-senha
CLICKHOUSE_PASSWORD=troque-esta-senha

# proxy/.env
CLICKHOUSE_PASSWORD=troque-esta-senha
```

> Os arquivos `.env` são versionados neste laboratório. Antes de compartilhar um fork ou publicar, troque as senhas e não faça commit delas.

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
  - Senha: a `CLICKHOUSE_PASSWORD`
  - Database: `zabbix`

  Clique em *Update* e depois em *Test*.
- **Administration → Proxies → Create proxy:** nome `proxy-apm-01`, modo *Active*, e na aba *APM* marque *Data collection enabled*. Salve.

> Os nomes dos campos seguem a interface da versão 8.0 RC1 e podem mudar em versões futuras.

### 5. Suba o proxy com APM

```bash
cd proxy
docker compose up -d --build
docker compose logs -f zabbix-proxy
```

A compilação leva vários minutos. Quando o container subir, o log deve indicar que o coletor OpenTelemetry está escutando na porta `14317`. Em *Administration → Proxies*, o campo *Last seen* do `proxy-apm-01` deve atualizar.

### 6. Suba o gateway

```bash
cd ../gateway
docker compose up -d
docker compose logs --tail=20 otel-gateway
```

O gateway escuta OTLP/gRPC em `4317` e envia para `zabbix-proxy:14317`.

### 7. Suba a aplicação de estudo (`shop/`)

```bash
cd ../shop
docker compose up -d --build
docker compose ps
```

Dois serviços sobem com o compose principal (`shop-db` e `shop-api`), e o `compose.override.yaml` é aplicado automaticamente, ligando métricas e logs nos serviços certos.

Os serviços são:

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

> Se logo após a subida aparecerem respostas `502 upstream unavailable`, é normal: o `shop-api` pode iniciar antes do `shop-users` e do `shop-orders` estarem prontos. Os próximos requests devem funcionar.

### 8. Valide os traces

Teste de fumaça direto no proxy (sem gateway):

```bash
docker run --rm --network host ghcr.io/open-telemetry/opentelemetry-collector-contrib/telemetrygen:latest \
  traces --otlp-insecure --otlp-endpoint localhost:14317 --service teste-manual --rate 5 --duration 30s
```

Ou pelo gateway, usando a porta `4317`, que é o caminho das aplicações:

```bash
docker run --rm --network host ghcr.io/open-telemetry/opentelemetry-collector-contrib/telemetrygen:latest \
  traces --otlp-insecure --otlp-endpoint localhost:4317 --service teste-manual --rate 5 --duration 30s
```

Depois, abra **APM → Traces** no frontend e confira. No ClickHouse:

```bash
cd ..
source .env
docker compose exec clickhouse clickhouse-client --user zabbix --password "$CLICKHOUSE_PASSWORD" \
  -q "SELECT ServiceName, count() AS spans, uniqExact(TraceId) AS traces FROM zabbix.otel_traces GROUP BY ServiceName ORDER BY spans DESC"
```

Você deve ver `shop-api`, `shop-users`, `shop-orders` e `teste-manual`.

## Cenários de tráfego

O `shop-loadgen` executa ações aleatórias com pesos diferentes, a cada 0,25 a 0,75 segundo por padrão. Ele sorteia as ações abaixo:

| Ação | Endpoint | Resultado esperado |
|---|---|---|
| Listar usuários | `GET /api/users` | 200 |
| Buscar usuário existente | `GET /api/users/{id}` | 200 |
| Criar usuário | `POST /api/users` | 201 |
| Renomear usuário | `PUT /api/users/{id}` | 200 |
| Apagar usuário de teste | `DELETE /api/users/{id}` | 200, ou **409** se o usuário tiver pedidos |
| Criar pedido | `POST /api/orders` | 201 |
| Listar pedidos | `GET /api/orders` | 200 |
| Atualizar status do pedido | `PUT /api/orders/{id}/status` | 200 |
| Apagar pedido | `DELETE /api/orders/{id}` | 200 |
| Relatório de pedidos | `GET /api/orders/report` | 200 |
| Resumo do usuário (fan-out) | `GET /api/summary/{id}` | 200 |

### Erros e lentidão provocados de propósito

| Ação | Endpoint | Status | Origem |
|---|---|---|---|
| Usuário inexistente | `GET /api/users/999999` | **404** | `shop-users` |
| Pedido com usuário fantasma | `POST /api/orders` com `user_id: 999999` | **404** | `shop-orders` (valida no `shop-users`) |
| Apagar usuário com pedidos | `DELETE /api/users/{id}` | **409** | `shop-users` (chave estrangeira) |
| Erro de banco | `GET /api/boom` | **500** | `shop-users` (tabela inexistente) |
| Consulta lenta | `GET /api/slow` | 200, com 1 a 3 s de latência | `shop-users` (`pg_sleep`) |

Esses erros são previsíveis e fazem parte do estudo. Para separar tráfego normal de erro provocado na análise, use o nome do endpoint ou a ação de origem.

Para gerar um cenário específico, rode só uma chamada:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/boom
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/slow
```

### Carga ajustável

Para mudar a intensidade do loadgen, edite a variável `INTERVAL` em `shop/compose.yaml` (tempo médio entre ações, em segundos) e rode `docker compose up -d shop-loadgen` dentro de `shop/`. Valores menores geram mais tráfego.

## Consultas úteis

Spans de erro por serviço (ajuste os valores de `StatusCode` conforme o que aparecer na sua tabela):

```bash
docker compose exec clickhouse clickhouse-client --user zabbix --password "$CLICKHOUSE_PASSWORD" \
  -q "SELECT ServiceName, StatusCode, count() FROM zabbix.otel_traces GROUP BY ServiceName, StatusCode ORDER BY count() DESC"
```

Itens *Telemetry query* no PostgreSQL (opcional, exige o template de OpenTelemetry importado no frontend):

```bash
docker compose exec postgres psql -U zabbix -d zabbix -c "SELECT i.key_, h.value, to_timestamp(h.clock) FROM history_uint h JOIN items i USING(itemid) WHERE i.key_ LIKE 'otlp.span%' ORDER BY h.clock DESC LIMIT 5"
```

## Parar e limpar

Pare o que não for mais necessário, na ordem inversa da subida:

```bash
cd shop && docker compose down
cd ../gateway && docker compose down
cd ../proxy && docker compose down
cd .. && docker compose down
```

Para apagar também os dados (volumes), use `docker compose down -v` na raiz. Depois disso, **recadastre o proxy** no frontend e recrie o container dele (`cd proxy && docker compose down && docker compose up -d`).

> Remover o volume do ClickHouse apaga os dados de traces. Remover o volume do PostgreSQL apaga o histórico do Zabbix.

## Observações

- **Tabelas do ClickHouse:** são criadas apenas quando o volume é novo. Em um volume existente, aplique uma vez:
  ```bash
  source .env
  for f in clickhouse-init/*.sql; do docker compose exec -T clickhouse clickhouse-client --user zabbix --password "$CLICKHOUSE_PASSWORD" --multiquery < "$f"; done
  ```
- **Não altere a ordem das colunas** dos SQLs em `clickhouse-init/`. O proxy insere os dados por posição.
- **Timestamps:** o proxy envia tempo como decimal (`1759700000.123456789`). Por isso as tabelas têm uma coluna `...Raw Decimal(19,9)` e a coluna `DateTime64` real como `MATERIALIZED`.
- **Retenção:** o housekeeper do Zabbix não limpa o ClickHouse. A limpeza é feita pelo TTL de 31 dias de cada tabela.
- **Portas abertas:** `8123` e `9000` do ClickHouse ficam acessíveis na rede do host. Para restringir, troque `"8123:8123"` por `"127.0.0.1:8123:8123"` no `docker-compose.yml`.
- **Versão:** o Zabbix 8.0 RC1 é uma versão de teste e pode ter mudanças até a versão final. As imagens usam `alpine-trunk`, que é a linha de desenvolvimento do 8.0.
- **Carga aleatória:** o loadgen usa geração aleatória sem semente fixa. Duas execuções nunca geram exatamente o mesmo tráfego, o que é importante considerar ao comparar cenários.

## Solução de problemas

| Sintoma | Causa provável | Ação |
|---|---|---|
| `network zabbix8_zbx declared as external, but could not be found` | A stack da raiz não está no ar | Suba a raiz primeiro (passo 3) |
| Proxy não aparece em *Administration → Proxies* | Proxy não cadastrado, ou nome diferente de `proxy-apm-01` | Cadastre o proxy no frontend (passo 4) |
| `502 upstream unavailable` no início | `shop-api` subiu antes do `shop-users` | Aguarde alguns segundos e repita |
| Traces não aparecem em APM → Traces | Gateway ou proxy fora do ar, ou data source APM sem *Test* ok | Confira os logs de `gateway/` e `proxy/` e o teste do data source |
| Porta 4317 ou 14317 em uso | Outro serviço usando a porta | Pare o serviço conflitante ou troque a porta no compose |
| `CLICKHOUSE_PASSWORD` não definido ao subir o proxy | `proxy/.env` ausente ou incompleto | Preencha `proxy/.env` (passo 2) |

## Referências

- [Release notes do Zabbix 8.0.0rc1](https://www.zabbix.com/rn/rn8.0.0rc1)
- [Documentação do Zabbix 8.0: APM e OpenTelemetry](https://www.zabbix.com/documentation/8.0)
- [zabbix_proxy.conf](https://github.com/zabbix/zabbix/blob/master/conf/zabbix_proxy.conf)

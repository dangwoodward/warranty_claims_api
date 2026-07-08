# Warranty Claim Analyzer

A FastAPI service that turns free-form repair-order (RO) text into a structured
warranty-coverage decision in JSON format

## AI Coding Tools Used

- I used Claude Code, specifically Opus 4.8 to help with organizing the repo and help with the initial scaffolding of this project.

- I used Langchain as an orchestration tool for all the AI calls and MCP tool calls. Claude Code API was used to pass the free form repair orders. OPENAI or any other tool can be switched out with only a few lines of code changes.

```
POST /analyze-claim
{ "ro_text": "RO# 847291 | VIN: 1G1FY6S00N0000123 | 2022 Chevrolet Bolt EV | ..." }
```

→

```json
{
  "vin": "1G1FY6S00N0000123",
  "year": 2022,
  "make": "Chevrolet",
  "model": "Bolt EV",
  "mileage": 12340,
  "repair_description": "Replaced high-voltage battery module",
  "part_number": "24299461",
  "labor_hours": 4.2,
  "coverage_eligible": true,
  "coverage_reason": "Vehicle within Voltec warranty: 8yr/100k miles"
}
```

## How it works

1. **Extraction (LangChain + Claude).** `main.py` uses
   `ChatAnthropic(model="claude-opus-4-8")` with `.with_structured_output()` to
   parse the RO text into the typed `ExtractedClaim` schema (`models.py`).
2. **Warranty check (MCP).** The provided `check_warranty_coverage` stub lives
   in `warranty_module.py` and is published as an MCP tool by
   `warranty_server.py`. The API is an MCP client: at startup it opens a
   persistent stdio session to that server and loads the tool into LangChain via
   `langchain-mcp-adapters`. Each request invokes the tool deterministically
   with the extracted fields.
3. **Merge & respond** with the combined `AnalyzeClaimResponse`.

```
RO text ──► LangChain/Claude (extract) ──► MCP tool (warranty) ──► response
                                             │
                              warranty_server.py ─► warranty_module.py (stub)
```

`check_warranty_coverage` is a plausible mock (VIN validation, EV/Voltec vs.
Powertrain vs. Bumper-to-Bumper tiers) — the point is the integration, not the
warranty logic.

See [ARCHITECTURE.md](ARCHITECTURE.md) for diagrams of the startup and per-request
flows and a step-by-step of the LangChain + MCP wiring.

## Run

### Docker Compose (recommended)

Brings up the API plus a monitoring stack (Prometheus + Grafana):

```bash
cp .env.example .env          # then put your ANTHROPIC_API_KEY in .env
docker compose up --build
```

| Service    | URL                   | Notes                                                           |
| ---------- | --------------------- | --------------------------------------------------------------- |
| API        | http://localhost:8000 | `/analyze-claim`, `/health`, `/metrics`, `/docs`                |
| Prometheus | http://localhost:9090 | scrapes the API's `/metrics` every 15s                          |
| Grafana    | http://localhost:3000 | login `admin` / `admin`; Prometheus datasource auto-provisioned |

### Docker (API only)

```bash
docker build -t warrcloud-api .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=sk-ant-... warrcloud-api
```

### Local

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
uvicorn main:app --reload
```

### Try it

```bash
curl -sS http://localhost:8000/analyze-claim \
  -H 'Content-Type: application/json' \
  -d '{"ro_text": "RO# 847291 | VIN: 1G1FY6S00N0000123 | 2022 Chevrolet Bolt EV | Mileage: 12,340 | Complaint: Battery warning light on, reduced range. | Repair: Replaced high-voltage battery module. | Parts: 24299461 (Battery Module Assembly) | Labor: 4.2 hrs | Tech: M. Rodriguez"}' | python3 -m json.tool
```

(`-sS` stays quiet on success but surfaces errors; piping to `python3 -m json.tool` pretty-prints the JSON so it doesn't get buried against your shell prompt.)

Interactive docs at `http://localhost:8000/docs`.

## Error handling

- Invalid VIN or unknown make/model → the MCP tool returns a structured `{"error": ...}`,
  surfaced as `422`.
- Missing `ANTHROPIC_API_KEY` → `500`.
- Extraction failure (LLM) → `502`.
- Warranty lookup failure (MCP/parse) → `502`.

## Observability (metrics)

The API exposes Prometheus metrics at `/metrics` via
`prometheus-fastapi-instrumentator` — request counts, latencies, and status codes,
labelled per route (e.g. `http_requests_total{handler="/analyze-claim"}`).

Under Compose, Prometheus scrapes those metrics and Grafana visualizes them:

1. `docker compose up --build`, then generate some traffic (`curl` the endpoint a few times).
2. Open the pre-built **WarrCloud API** dashboard at
   http://localhost:3000/d/warrcloud-api/warrcloud-api (`admin` / `admin`). Both the
   Prometheus datasource and this dashboard are auto-provisioned from
   [grafana/provisioning/](grafana/provisioning/) — no manual setup. It shows two
   stat panels: **claims succeeded** (`2xx`) and **claims processed with errors**
   (`4xx`/`5xx`), scoped to `/analyze-claim`.
3. Prometheus at http://localhost:9090 — try a query like
   `rate(http_requests_total[1m])`.

> **Metrics, not logs.** Prometheus + Grafana here is **metrics** monitoring (counts,
> rates, latencies). For searchable application **logs** ("which VIN failed and why"),
> add Grafana Loki + a log shipper (Alloy/Promtail) — a natural next step on the same
> Grafana stack.

> **Persistence caveat.** Metric _history_ is currently ephemeral: the API's counters
> reset when its container restarts, and Prometheus stores its TSDB in an anonymous
> volume that does **not** survive `docker compose down`. The Grafana dashboard
> definition itself is durable (it's provisioned from a file). To make history
> persist, give Prometheus a named volume + a `--storage.tsdb.retention.time` flag.

## Repository layout

| Path                    | Purpose                                                                                         |
| ----------------------- | ----------------------------------------------------------------------------------------------- |
| `main.py`               | FastAPI app: `/analyze-claim`, `/health`, `/metrics`; orchestrates extraction + warranty lookup |
| `models.py`             | Request / extraction / response Pydantic schemas                                                |
| `warranty_module.py`    | The provided `check_warranty_coverage` stub                                                     |
| `warranty_server.py`    | MCP server exposing the stub as a tool                                                          |
| `Dockerfile`            | API image                                                                                       |
| `docker-compose.yml`    | API + Prometheus + Grafana stack                                                                |
| `prometheus.yml`        | Prometheus scrape config                                                                        |
| `grafana/provisioning/` | Auto-provisioned datasource + dashboard                                                         |
| `.env.example`          | Template for `ANTHROPIC_API_KEY` (copy to `.env`)                                               |
| `ARCHITECTURE.md`       | Diagrams + LangChain/MCP walkthrough                                                            |

## Notes

- Model id: `claude-opus-4-8`.
- The MCP server runs in-process-adjacent (spawned as a stdio subprocess by the
  API), so a single container is all that's needed.

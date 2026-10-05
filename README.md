# Order Tracker

> **AI Dev Tools Zoomcamp — Homework 04:** This repository is a fork of the Order Tracker starter project, extended for the Week 4 DevOps and observability assignment. The completed coursework adds OpenTelemetry metrics, logs, and traces; an OpenTelemetry Collector with Prometheus, Loki, Tempo, and Grafana; a 5xx alert; and a webhook-triggered coding-agent responder.

A small order tracking app for the AI Dev Tools Zoomcamp observability homework. It includes a web page, API, tests, and a Docker Compose setup. You add telemetry, alerts, and an incident responder in Homework 4.

The main user flow is creating an order and checking its status. Three sample orders are created on first startup.

## Run it

You need Docker with Compose. To run the tests, you also need Python 3.11+ and `uv`.

```bash
docker compose up --build -d --wait
```

Open <http://127.0.0.1:8000>. The API is at `/api/orders`, and the health check is at `/healthz`. Data is stored in a Docker volume and survives container recreation.

## Observability

Compose also starts an OpenTelemetry Collector, Prometheus, Loki, Tempo, and Grafana. The app sends metrics, logs, and traces to the Collector over OTLP. Grafana is available at <http://127.0.0.1:3000> (`admin` / `admin`); the provisioned **Order Tracker Requests** dashboard shows lookup request counts, 5xx errors, and request rate by route and status.

To generate telemetry:

```bash
curl -i http://localhost:8000/api/orders/standard-1002
```

Use Grafana Explore with the Loki and Tempo data sources to inspect the matching log and trace.

Grafana also provisions an **Order lookup server errors** alert. It evaluates lookup 5xx responses over five minutes every ten seconds, links to the request dashboard, treats periods with no matching data as normal, and sends firing notifications to the `incident-responder` webhook contact point.

## Incident responder

The `incident-response` service receives Grafana webhooks at `POST /alerts` on port `8001`. It writes each alert, recent Loki logs, Tempo traces, and the coding-agent result to the `incidents` Docker volume. It then invokes Codex headlessly with `codex exec --sandbox danger-full-access` in its dedicated responder container, so the agent can read the saved incident evidence and investigate the mounted repository. When `OPENAI_API_KEY` is supplied to Compose, the responder initializes Codex's non-interactive API-key login during startup.

The response returns an incident ID; retrieve its alert, evidence location, agent status, and saved final output at `GET /incidents/{incident-id}`.

Send the homework test notification with:

```bash
curl -X POST http://localhost:8001/alerts \
  -H 'Content-Type: application/json' \
  -d '{"alerts":[{"status":"firing","labels":{"alertname":"ResponderTest","test":"true"},"annotations":{"summary":"Test notification; no incident to fix"}}]}'
```

If port 8000 is occupied, set `ORDER_TRACKER_PORT`, for example:

```bash
ORDER_TRACKER_PORT=18080 docker compose up --build -d --wait
```

Run tests with `uv run --frozen pytest -q`. Stop the app with `docker compose down`. Add `-v` only if you also want to delete the order data.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Web page |
| GET | `/healthz` | Database health check |
| GET | `/api/orders` | List orders |
| POST | `/api/orders` | Create an order |
| GET | `/api/orders/{id}` | Check an order |
| PATCH | `/api/orders/{id}` | Change an order status |

The app uses SQLite to keep setup small. Run one app container at a time. The course exercise is about detecting and handling an incident, not scaling the database.

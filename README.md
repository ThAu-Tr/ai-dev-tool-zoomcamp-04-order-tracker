# Order Tracker

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

Grafana also provisions an **Order lookup server errors** alert. It evaluates lookup 5xx responses over five minutes every ten seconds, links to the request dashboard, and treats periods with no matching data as normal.

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

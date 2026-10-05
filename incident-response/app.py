"""Persist Grafana alert evidence and dispatch Codex for incident triage."""

import asyncio
import json
import os
import shlex
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field


INCIDENT_DIR = Path(os.getenv("INCIDENT_DIR", "data/incidents"))
LOKI_URL = os.getenv("LOKI_URL", "http://localhost:3100")
TEMPO_URL = os.getenv("TEMPO_URL", "http://localhost:3200")
CODEX_COMMAND = os.getenv("CODEX_COMMAND", "codex exec --sandbox workspace-write")
CODEX_TIMEOUT_SECONDS = int(os.getenv("CODEX_TIMEOUT_SECONDS", "900"))
WORKSPACE = Path(os.getenv("WORKSPACE", "/workspace"))

app = FastAPI(title="Order Tracker Incident Responder")


class GrafanaAlertPayload(BaseModel):
    alerts: list[dict[str, Any]] = Field(default_factory=list)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def affected_endpoint(alert: dict[str, Any]) -> str:
    labels = alert.get("labels", {})
    annotations = alert.get("annotations", {})
    return annotations.get("endpoint") or labels.get("endpoint") or labels.get("http_route") or "unknown"


async def get_json(client: httpx.AsyncClient, url: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return {"ok": True, "data": response.json()}
    except (httpx.HTTPError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}


async def collect_evidence(alert: dict[str, Any]) -> dict[str, Any]:
    """Collect recent service logs and route-specific traces without failing the alert handler."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=15)
    endpoint = affected_endpoint(alert)
    async with httpx.AsyncClient(timeout=10) as client:
        logs, traces = await asyncio.gather(
            get_json(
                client,
                f"{LOKI_URL}/loki/api/v1/query_range",
                {
                    "query": '{service_name="order-tracker"}',
                    "start": str(int(start.timestamp() * 1_000_000_000)),
                    "end": str(int(now.timestamp() * 1_000_000_000)),
                    "limit": 100,
                },
            ),
            get_json(client, f"{TEMPO_URL}/api/search", {"tags": f"http.route={endpoint}", "limit": 20}),
        )
    return {
        "collected_at": now.isoformat(),
        "endpoint": endpoint,
        "time_window": {"from": start.isoformat(), "to": now.isoformat()},
        "logs": logs,
        "traces": traces,
    }


def build_prompt(incident_path: Path, alert: dict[str, Any], endpoint: str) -> str:
    is_test = alert.get("labels", {}).get("test") == "true"
    instruction = (
        "This is a responder test notification. Summarize the evidence only; do not modify the repository."
        if is_test
        else "Investigate the incident, implement and verify a safe fix when appropriate, then summarize the outcome."
    )
    return f"""You are the automated incident responder for Order Tracker.

{instruction}
The affected endpoint is: {endpoint}
The raw Grafana alert is in {incident_path / 'alert.json'}.
Collected logs and traces are in {incident_path / 'evidence.json'}.
Work in {WORKSPACE}. Record a concise final conclusion, including any tests run.
"""


async def run_coding_agent(incident_path: Path, alert: dict[str, Any], endpoint: str) -> None:
    output_path = incident_path / "agent-output.txt"
    result_path = incident_path / "agent-result.json"
    command = shlex.split(CODEX_COMMAND)
    prompt = build_prompt(incident_path, alert, endpoint)
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            prompt,
            cwd=WORKSPACE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=CODEX_TIMEOUT_SECONDS)
        output_path.write_text(stdout.decode(errors="replace") + stderr.decode(errors="replace"), encoding="utf-8")
        write_json(
            result_path,
            {"status": "completed" if process.returncode == 0 else "failed", "exit_code": process.returncode},
        )
    except FileNotFoundError:
        output_path.write_text(f"Coding assistant command was not found: {CODEX_COMMAND}\n", encoding="utf-8")
        write_json(result_path, {"status": "failed", "error": "coding assistant command not found"})
    except TimeoutError:
        output_path.write_text("Coding assistant timed out.\n", encoding="utf-8")
        write_json(result_path, {"status": "timed_out", "timeout_seconds": CODEX_TIMEOUT_SECONDS})
    except Exception as exc:  # Keep alert intake available even if the agent cannot start.
        output_path.write_text(f"Coding assistant failed to start: {exc}\n", encoding="utf-8")
        write_json(result_path, {"status": "failed", "error": str(exc)})


@app.on_event("startup")
async def create_incident_directory() -> None:
    INCIDENT_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/alerts", status_code=202)
async def receive_alert(payload: GrafanaAlertPayload, background_tasks: BackgroundTasks) -> dict[str, Any]:
    incidents = []
    for alert in payload.alerts:
        incident_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
        incident_path = INCIDENT_DIR / incident_id
        incident_path.mkdir(parents=True)
        endpoint = affected_endpoint(alert)
        write_json(incident_path / "alert.json", alert)
        evidence = await collect_evidence(alert)
        write_json(incident_path / "evidence.json", evidence)
        background_tasks.add_task(run_coding_agent, incident_path, alert, endpoint)
        incidents.append({"id": incident_id, "endpoint": endpoint, "status": "agent_started"})
    return {"incidents": incidents}


@app.get("/incidents/{incident_id}")
async def incident_status(incident_id: str) -> dict[str, Any]:
    incident_path = INCIDENT_DIR / incident_id
    if not incident_path.is_dir():
        raise HTTPException(404, "Incident not found")
    result_path = incident_path / "agent-result.json"
    output_path = incident_path / "agent-output.txt"
    return {
        "id": incident_id,
        "alert": json.loads((incident_path / "alert.json").read_text(encoding="utf-8")),
        "evidence_path": str(incident_path / "evidence.json"),
        "agent": json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {"status": "running"},
        "agent_output": output_path.read_text(encoding="utf-8") if output_path.exists() else None,
    }

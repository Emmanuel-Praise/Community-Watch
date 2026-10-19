import hashlib
import hmac
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import bot
import config
import db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

db.init_db()

app = FastAPI(
    title=config.APP_NAME,
    version="1.0.0",
    description="Simplified Community Watch API with a WhatsApp bot.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if config.CORS_ALLOW_ALL else config.CORS_ORIGINS,
    allow_credentials=False if config.CORS_ALLOW_ALL else True,
    allow_methods=["*"],
    allow_headers=["*"],
)

REPORT_TYPES = {
    "robbery",
    "theft",
    "vandalism",
    "fire",
    "flood",
    "suspicious_activity",
    "medical_emergency",
    "violence",
    "other",
}
SEVERITIES = {"low", "medium", "high"}
REPORT_STATUSES = {"pending", "under_review", "verified", "dismissed"}
HEAD_STATUSES = {"pending", "verified", "rejected"}


def clean_text(value: Any, limit: int) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()[:limit]


def optional_number(value: Any, name: str, minimum: float, maximum: float) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{name} must be a number.") from exc
    if not minimum <= number <= maximum:
        raise HTTPException(
            status_code=400,
            detail=f"{name} must be between {minimum} and {maximum}.",
        )
    return round(number, 6)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "app": config.APP_NAME,
        "version": "1.0.0",
        "whatsapp_configured": bot.is_configured(),
        "ai_configured": bool(config.OPENROUTER_API_KEY),
        "voice_configured": bool(config.ELEVENLABS_API_KEY),
    }


@app.get("/api/stats")
def get_stats() -> dict:
    return db.stats()


@app.get("/api/reports")
def get_reports(
    report_type: str | None = Query(default=None, alias="type"),
    status: str | None = None,
    search: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
) -> list[dict]:
    if report_type and report_type not in REPORT_TYPES:
        raise HTTPException(status_code=400, detail="Unknown report type.")
    if status and status not in REPORT_STATUSES:
        raise HTTPException(status_code=400, detail="Unknown report status.")
    return db.list_reports(
        report_type=report_type,
        status=status,
        search=search,
        limit=limit,
    )


@app.post("/api/reports", status_code=201)
def create_report(data: dict) -> dict:
    description = clean_text(data.get("description"), 2000)
    if len(description) < 5:
        raise HTTPException(
            status_code=400,
            detail="Description must be at least 5 characters.",
        )
    report_type = clean_text(data.get("type"), 50) or "other"
    if report_type not in REPORT_TYPES:
        raise HTTPException(status_code=400, detail="Unknown report type.")
    severity = clean_text(data.get("severity"), 20) or "low"
    if severity not in SEVERITIES:
        raise HTTPException(status_code=400, detail="Severity must be low, medium or high.")

    report = db.create_report(
        {
            "type": report_type,
            "severity": severity,
            "priority": severity,
            "description": description,
            "latitude": optional_number(data.get("latitude"), "Latitude", -90, 90),
            "longitude": optional_number(data.get("longitude"), "Longitude", -180, 180),
            "location_name": clean_text(data.get("location_name"), 200) or None,
            "status": "pending",
            "source": "manual",
            "occurred_at": clean_text(data.get("occurred_at"), 40) or None,
        }
    )
    return report


@app.get("/api/reports/{report_id}")
def get_report(report_id: int) -> dict:
    report = db.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
    return report


@app.patch("/api/reports/{report_id}/status")
def update_report_status(report_id: int, data: dict) -> dict:
    status = clean_text(data.get("status"), 20)
    if status not in REPORT_STATUSES:
        raise HTTPException(status_code=400, detail="Unknown report status.")
    report = db.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
    if report["status"] == "dismissed" and status != "dismissed":
        raise HTTPException(status_code=400, detail="Dismissed reports cannot be reopened.")
    return db.update_report_status(report_id, status)


@app.patch("/api/reports/{report_id}/location")
def update_report_location(report_id: int, data: dict) -> dict:
    report = db.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
    latitude = optional_number(data.get("latitude"), "Latitude", -90, 90)
    longitude = optional_number(data.get("longitude"), "Longitude", -180, 180)
    if latitude is None or longitude is None:
        raise HTTPException(status_code=400, detail="Latitude and longitude are required.")
    return db.update_report_location(report_id, latitude, longitude)


@app.delete("/api/reports/{report_id}", status_code=204)
def remove_report(report_id: int) -> Response:
    if not db.delete_report(report_id):
        raise HTTPException(status_code=404, detail="Report not found.")
    return Response(status_code=204)


@app.get("/api/reports/{report_id}/matching-heads")
def matching_heads(report_id: int) -> list[dict]:
    report = db.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
    return db.matching_heads_for_report(report)


@app.get("/api/quarter-heads")
def get_quarter_heads(status: str | None = None) -> list[dict]:
    if status and status not in HEAD_STATUSES:
        raise HTTPException(status_code=400, detail="Unknown quarter-head status.")
    return db.list_heads(status)


@app.post("/api/quarter-heads", status_code=201)
def register_quarter_head(data: dict) -> dict:
    name = clean_text(data.get("name"), 120)
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Full name is required.")
    wa_number = "".join(
        character
        for character in str(data.get("wa_number") or "")
        if character.isdigit() or character == "+"
    )
    if len(wa_number) < 5:
        raise HTTPException(status_code=400, detail="A valid WhatsApp number is required.")
    quarter_name = clean_text(data.get("quarter_name"), 150)
    if len(quarter_name) < 2:
        raise HTTPException(status_code=400, detail="Quarter or area name is required.")
    return db.create_head(
        {
            "name": name,
            "wa_number": wa_number,
            "quarter_name": quarter_name,
            "city": clean_text(data.get("city"), 150) or None,
            "latitude": optional_number(data.get("latitude"), "Latitude", -90, 90),
            "longitude": optional_number(data.get("longitude"), "Longitude", -180, 180),
            "notes": clean_text(data.get("notes"), 1000) or None,
            "status": "pending",
        }
    )


@app.patch("/api/quarter-heads/{head_id}/status")
def update_head_status(head_id: int, data: dict) -> dict:
    status = clean_text(data.get("status"), 20)
    if status not in HEAD_STATUSES:
        raise HTTPException(status_code=400, detail="Unknown quarter-head status.")
    if not db.get_head(head_id):
        raise HTTPException(status_code=404, detail="Quarter head not found.")
    return db.set_head_status(head_id, status)


@app.get("/api/whatsapp/status")
def whatsapp_status() -> dict:
    return {
        "configured": bot.is_configured(),
        "verify_token_configured": bool(config.WHATSAPP_VERIFY_TOKEN),
        "ai_configured": bool(config.OPENROUTER_API_KEY),
        "voice_configured": bool(config.ELEVENLABS_API_KEY),
        "bot_name": config.BOT_NAME,
    }


@app.get("/api/whatsapp/webhook")
def verify_webhook(request: Request):
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode is None and token is None and challenge is None:
        return {
            "status": "ok",
            "service": "WhatsApp webhook",
            "bot": config.BOT_NAME,
            "configured": bot.is_configured(),
            "hint": (
                "Add ?hub.mode=subscribe&hub.verify_token=<token>"
                "&hub.challenge=123 to test verification."
            ),
        }
    if (
        mode == "subscribe"
        and token == config.WHATSAPP_VERIFY_TOKEN
        and challenge is not None
    ):
        return Response(content=challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Webhook verification failed.")


def signature_ok(raw_body: bytes, signature: str | None) -> bool:
    if not config.WHATSAPP_APP_SECRET:
        return True
    if not signature:
        return False
    expected = "sha256=" + hmac.new(
        config.WHATSAPP_APP_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@app.post("/api/whatsapp/webhook")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks) -> dict:
    raw_body = await request.body()
    if not signature_ok(raw_body, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(status_code=401, detail="Invalid webhook signature.")
    try:
        payload = json.loads(raw_body or b"{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid webhook payload.")
    background_tasks.add_task(bot.process_webhook_payload, payload)
    return {"received": True, "processing": "background"}


# Serve the plain frontend from the same web service.
# Locally: http://localhost:8000/
# On Render: https://your-service.onrender.com/
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

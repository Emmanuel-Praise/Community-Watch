import hashlib
import logging
import re
import time
from typing import Any

import httpx

import ai
import config
import db

logger = logging.getLogger("community_watch.bot")

GREETINGS = {
    "hi",
    "hello",
    "hey",
    "salut",
    "bonjour",
    "bonsoir",
    "good morning",
    "good afternoon",
    "good evening",
    "start",
}

THANKS = {"thanks", "thank you", "thankyou", "merci", "merci beaucoup", "thx"}

HELP_WORDS = {"help", "menu", "info", "infos", "aide"}

REGISTER_PHRASES = {
    "quarter head",
    "quarterhead",
    "quarter-head",
    "chef de quartier",
    "chef du quartier",
    "chef quartier",
    "register as head",
    "become head",
    "become a head",
    "i want to register",
    "i wanna register",
    "i need to register",
    "je veux m'inscrire",
    "je veux devenir chef",
    "devenir chef",
    "register me",
    "sign me up",
}

REPORT_PHRASES = {
    "i want to report",
    "i wanna report",
    "want to report",
    "report an incident",
    "report something",
    "report a case",
    "i have a report",
    "i need to report",
    "let me report",
    "how do i report",
    "how to report",
    "how can i report",
    "je veux signaler",
    "je veux faire un signalement",
}

CAPABILITY_PHRASES = {
    "what can you do",
    "what do you do",
    "who are you",
    "who is this",
    "how does this work",
    "how do you work",
    "how does it work",
    "what is this",
    "what's this",
    "what is community watch",
    "que peux-tu faire",
    "qui es-tu",
}

INCIDENT_KEYWORDS = set()
for _type, _words in ai.TYPE_KEYWORDS:
    INCIDENT_KEYWORDS.update(_words)
INCIDENT_KEYWORDS.update(
    {
        "accident",
        "crash",
        "emergency",
        "dead",
        "body",
        "drown",
        "riot",
        "protest",
        "missing",
        "lost child",
        "trapped",
        "blocked road",
        "fallen tree",
        "rogue",
        "wahala",
        "palava",
        "chakara",
        "urgence",
        "accident",
        "disparu",
        "coince",
    }
)

LOCATION_CUES = (
    " near ",
    " behind ",
    " opposite ",
    " next to ",
    " along ",
    " around ",
    " street",
    " road",
    " market",
    " bus stop",
    " quarter",
    " village",
    " town",
    " pres ",
    " derriere ",
    " marche ",
    " rue ",
    " route ",
    " quartier ",
)

PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

MIME_SUFFIX = {
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/amr": ".amr",
    "audio/aac": ".aac",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
}

CHAT_STATE: dict[str, dict] = {}
STATE_TTL_SECONDS = 30 * 60

SEEN_MESSAGES: dict[str, float] = {}
SEEN_TTL_SECONDS = 24 * 60 * 60
SEEN_MAX = 2000


def normalize(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def contains_any(text: str, phrases: set[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def looks_like_incident(text: str) -> bool:
    lower = text.lower()
    if contains_any(lower, INCIDENT_KEYWORDS):
        return True
    if len(text.split()) >= 6 and any(cue in lower for cue in LOCATION_CUES):
        return True
    return False


def is_register_intent(text: str) -> bool:
    return contains_any(text.lower(), REGISTER_PHRASES)


def is_report_intent(text: str) -> bool:
    return contains_any(text.lower(), REPORT_PHRASES)


def is_capability_question(text: str) -> bool:
    return contains_any(text.lower(), CAPABILITY_PHRASES)


def is_generic_question(text: str) -> bool:
    return text.strip().endswith("?") and not looks_like_incident(text)


def scrub(text: str) -> str:
    text = PHONE_RE.sub("[phone hidden]", text or "")
    text = EMAIL_RE.sub("[email hidden]", text)
    return " ".join(text.split()).strip()


def hash_number(number: str) -> str:
    return hashlib.sha256(number.strip().encode("utf-8")).hexdigest()


def _cleanup_state() -> None:
    now = time.time()
    for number in list(CHAT_STATE):
        if now - CHAT_STATE[number].get("ts", 0) > STATE_TTL_SECONDS:
            CHAT_STATE.pop(number, None)


def get_state(number: str) -> dict:
    _cleanup_state()
    return CHAT_STATE.get(number, {})


def set_state(number: str, step: str, **data: Any) -> None:
    CHAT_STATE[number] = {"step": step, "ts": time.time(), **data}


def clear_state(number: str) -> None:
    CHAT_STATE.pop(number, None)


def already_seen(message_id: str) -> bool:
    if not message_id:
        return False
    now = time.time()
    for seen_id in list(SEEN_MESSAGES):
        if now - SEEN_MESSAGES[seen_id] > SEEN_TTL_SECONDS:
            SEEN_MESSAGES.pop(seen_id, None)
        else:
            break
    if message_id in SEEN_MESSAGES:
        return True
    SEEN_MESSAGES[message_id] = now
    if len(SEEN_MESSAGES) > SEEN_MAX:
        SEEN_MESSAGES.pop(next(iter(SEEN_MESSAGES)))
    return False


def is_configured() -> bool:
    return bool(config.WHATSAPP_ACCESS_TOKEN and config.WHATSAPP_PHONE_NUMBER_ID)


def graph_url() -> str:
    return (
        f"https://graph.facebook.com/{config.GRAPH_VERSION}/"
        f"{config.WHATSAPP_PHONE_NUMBER_ID}/messages"
    )


def send_text(to: str, text: str) -> bool:
    if not is_configured():
        logger.warning("WhatsApp reply skipped: credentials are not configured.")
        return False
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text[:4000]},
    }
    try:
        response = httpx.post(
            graph_url(),
            headers={
                "Authorization": "Bearer " + config.WHATSAPP_ACCESS_TOKEN,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15,
        )
    except httpx.HTTPError:
        logger.warning("WhatsApp reply could not be delivered.", exc_info=True)
        return False
    if response.status_code >= 400:
        logger.warning(
            "WhatsApp send failed with status %s: %s",
            response.status_code,
            response.text[:300],
        )
        return False
    return True


def mark_read(message_id: str) -> None:
    if not is_configured() or not message_id:
        return
    try:
        httpx.post(
            graph_url(),
            headers={
                "Authorization": "Bearer " + config.WHATSAPP_ACCESS_TOKEN,
                "Content-Type": "application/json",
            },
            json={
                "messaging_product": "whatsapp",
                "status": "read",
                "message_id": message_id,
            },
            timeout=10,
        )
    except httpx.HTTPError:
        pass


def download_media(media_id: str) -> tuple[bytes, str]:
    if not is_configured():
        raise RuntimeError("WhatsApp media download is not configured.")
    headers = {"Authorization": "Bearer " + config.WHATSAPP_ACCESS_TOKEN}
    meta_url = f"https://graph.facebook.com/{config.GRAPH_VERSION}/{media_id}"
    try:
        meta_response = httpx.get(meta_url, headers=headers, timeout=30)
    except httpx.HTTPError as exc:
        raise RuntimeError("The attachment could not be fetched.") from exc
    if meta_response.status_code >= 400:
        raise RuntimeError("The attachment could not be fetched.")
    meta = meta_response.json()
    file_url = meta.get("url")
    mime_type = meta.get("mime_type") or ""
    if not file_url:
        raise RuntimeError("The attachment has no download URL.")
    try:
        file_response = httpx.get(file_url, headers=headers, timeout=60)
    except httpx.HTTPError as exc:
        raise RuntimeError("The attachment could not be downloaded.") from exc
    if file_response.status_code >= 400:
        raise RuntimeError("The attachment could not be downloaded.")
    data = file_response.content
    if not data:
        raise RuntimeError("The attachment was empty.")
    if len(data) > config.VOICE_MAX_BYTES:
        raise RuntimeError("That attachment is too large.")
    return data, mime_type


def greeting_reply(name: str = "") -> str:
    hello = f"Hello {name}! " if name else "Hello! "
    return (
        f"{hello}Welcome to *{config.BOT_NAME}*.\n\n"
        "I record anonymous safety reports for your community.\n\n"
        "Describe what happened in one message, for example:\n"
        "\"Armed robbery on Oxford Street, two men near the bus stop.\"\n\n"
        "Type *help* for examples. Your phone number is never stored with the report."
    )


def help_reply() -> str:
    return (
        f"*{config.BOT_NAME}* - how to report\n\n"
        "Send one message per incident with:\n"
        "1. What happened\n"
        "2. Where (street, area, landmark)\n"
        "3. When (now, 10 minutes ago, last night)\n\n"
        "Examples:\n"
        "- Fire behind Kantamanto market, smoke from a shop, 20 minutes ago.\n"
        "- Flooding at Kaneshie market, road blocked, happening now.\n\n"
        "Other commands:\n"
        "- hi - welcome message\n"
        "- thanks - close the chat\n"
        "- register as quarter head - receive reports from your area\n\n"
        "You can also send a voice note instead of typing.\n"
        "For danger right now, call local emergency services first."
    )


def thanks_reply() -> str:
    return (
        f"You are welcome. *{config.BOT_NAME}* is here 24/7.\n"
        "Send another report anytime and stay safe."
    )


def capability_reply(name: str = "") -> str:
    hello = f"Hello {name}. " if name else ""
    return (
        f"{hello}I am *{config.BOT_NAME}*, your community safety assistant.\n\n"
        "I can:\n"
        "- Record anonymous incident reports (robbery, fire, flood and more)\n"
        "- Understand voice notes\n"
        "- Send reports to the community dashboard\n"
        "- Register you as a quarter head for your area\n\n"
        "To report, tell me what happened, where and when.\n"
        "Type *help* for examples."
    )


def ask_details_reply() -> str:
    return (
        "Of course, I am listening.\n\n"
        "Tell me in one message:\n"
        "1. What happened?\n"
        "2. Where exactly (street, area, landmark)?\n"
        "3. When (now, 10 minutes ago, last night)?\n\n"
        "Example: \"Two men snatched a bag near the bus stop on Oxford Street, 10 minutes ago.\""
    )


def clarify_reply() -> str:
    return (
        "I want to get this right.\n\n"
        "Are you trying to report an incident? If yes, describe it like:\n"
        "\"Fire behind Kantamanto market, happening now.\"\n\n"
        "Or type *help* to see what I can do."
    )


def ask_location_reply() -> str:
    return (
        "One more thing so the right quarter head can find it.\n\n"
        "Which quarter or town did this happen in?\n"
        "Example: \"Mokolo, Yaounde\"\n\n"
        "You can also share your location with the attachment button."
    )


def confirmation_reply(incident_type: str, priority: str, report_id: int | None) -> str:
    reference = f" (ref #{report_id})" if report_id else ""
    label = incident_type.replace("_", " ").title()
    return (
        f"Report received{reference}. Thank you.\n\n"
        f"Type: *{label}*\n"
        f"Priority: *{priority.title()}*\n\n"
        "Our team will review it on the dashboard. "
        "Send more details anytime in a new message."
    )


def head_alert_text(report: dict) -> str:
    area = (report.get("location_name") or "your area").strip() or "your area"
    incident_type = str(report.get("type") or "incident").replace("_", " ").title()
    summary = (report.get("ai_summary") or report.get("description") or "")[:300]
    return (
        f"New report in {area}\n\n"
        f"Type: *{incident_type}*\n"
        f"Priority: *{str(report.get('priority', 'low')).title()}*\n"
        f"Ref: #{report.get('id')}\n\n"
        f"{summary}\n\n"
        f"Via *{config.BOT_NAME}*"
    )


def split_area(area_text: str) -> tuple[str, str | None]:
    clean = " ".join(area_text.split())[:200]
    if "," in clean:
        quarter, city = clean.split(",", 1)
        return quarter.strip() or clean, city.strip() or None
    return clean, None


def notify_heads(report: dict, skip_number: str = "") -> int:
    if not report:
        return 0
    sent = 0
    try:
        heads = db.matching_head_rows(report)
        for head in heads:
            number = head["wa_number"]
            if not number or number == skip_number:
                continue
            if send_text(number, head_alert_text(report)):
                sent += 1
    except Exception:
        logger.exception("Quarter-head notification failed.")
    return sent


def create_report_from_text(text: str, from_number: str, source: str = "whatsapp") -> int:
    cleaned = scrub(text)
    if len(cleaned) < 3:
        send_text(from_number, "Please describe the incident in a little more detail.")
        return 0
    try:
        extraction = ai.extract_incident(cleaned)
        report = db.create_report(
            {
                "type": extraction["type"],
                "severity": extraction["priority"],
                "priority": extraction["priority"],
                "description": extraction["summary"],
                "transcript": cleaned[:8000],
                "ai_summary": extraction["summary"],
                "details": extraction["details"],
                "location_name": extraction["location_name"],
                "latitude": extraction["latitude"],
                "longitude": extraction["longitude"],
                "status": "pending",
                "source": source,
                "anonymous_id_sha256": hash_number(from_number),
                "ai_processed": extraction["ai_processed"],
                "ai_error": extraction["ai_error"],
            }
        )
        if not report:
            raise RuntimeError("The report could not be saved.")
        send_text(
            from_number,
            confirmation_reply(report["type"], report["priority"], report["id"]),
        )
        if not report.get("location_name") and report.get("latitude") is None:
            set_state(from_number, "awaiting_location", report_id=report["id"])
            send_text(from_number, ask_location_reply())
        else:
            notify_heads(report, skip_number=from_number)
        return 1
    except Exception:
        logger.exception("Report processing failed.")
        send_text(
            from_number,
            "Sorry, I could not save that report just now. Please try again with "
            "what happened, where it happened, and when.",
        )
        return 0


def handle_registration_text(body: str, from_number: str, state: dict) -> int | None:
    step = state.get("step")
    if step == "qh_name":
        if looks_like_incident(body) or is_report_intent(body) or is_capability_question(body):
            clear_state(from_number)
            return None
        name = " ".join(body.split())[:120]
        if len(name) < 2:
            send_text(from_number, "Please tell me your full name to continue registration.")
            return 0
        set_state(from_number, "qh_area", name=name)
        send_text(
            from_number,
            f"{name.split()[0]}, noted.\n\n"
            "Which quarter are you head of, and in which town or city?\n"
            "Example: \"Mokolo quarter, Yaounde\"",
        )
        return 0

    if step == "qh_area":
        if looks_like_incident(body):
            clear_state(from_number)
            return None
        area = " ".join(body.split())[:200]
        if len(area) < 2:
            send_text(
                from_number,
                "Which quarter and town are you head of? "
                "Example: \"Mokolo quarter, Yaounde\"",
            )
            return 0
        quarter, city = split_area(area)
        db.create_head(
            {
                "name": state.get("name", ""),
                "wa_number": from_number,
                "quarter_name": quarter,
                "city": city,
                "status": "pending",
            }
        )
        clear_state(from_number)
        send_text(
            from_number,
            "Registration received.\n\n"
            "Our team will verify your details shortly. "
            "Once verified, you will receive new reports from your area on WhatsApp.\n\n"
            "Thank you for watching over your community.",
        )
        return 0

    return None


def handle_location_text(body: str, from_number: str, state: dict) -> int | None:
    if looks_like_incident(body):
        clear_state(from_number)
        return None
    location = " ".join(body.split())[:200]
    if len(location) < 2:
        send_text(from_number, ask_location_reply())
        return 0
    report_id = state.get("report_id")
    report = db.get_report(report_id) if report_id else None
    if not report:
        clear_state(from_number)
        send_text(from_number, "That report is no longer available. Please send a new report.")
        return 0
    report = db.update_report_location(
        report_id,
        report.get("latitude"),
        report.get("longitude"),
        location_name=location,
    )
    clear_state(from_number)
    sent = notify_heads(report, skip_number=from_number)
    if sent:
        send_text(
            from_number,
            f"Location saved for report #{report_id}.\n"
            f"I forwarded it to {sent} quarter head(s) in that area.",
        )
    else:
        send_text(
            from_number,
            f"Location saved for report #{report_id}.\n"
            "Our team will route it to the right quarter head.",
        )
    return 0


def handle_text(body: str, from_number: str, source: str = "whatsapp") -> int:
    body = (body or "").strip()
    if not body:
        return 0

    short = normalize(body)
    if short in GREETINGS:
        send_text(from_number, greeting_reply())
        return 0
    if short in THANKS:
        send_text(from_number, thanks_reply())
        return 0
    if short in HELP_WORDS or body == "?":
        send_text(from_number, help_reply())
        return 0
    if len(short) < 4:
        send_text(
            from_number,
            "Could you describe the incident in a little more detail? "
            "Example: \"Theft near Nungua market, this morning.\"",
        )
        return 0

    state = get_state(from_number)
    step = state.get("step", "")

    if is_capability_question(body):
        clear_state(from_number)
        send_text(from_number, capability_reply())
        return 0

    if step in ("qh_name", "qh_area"):
        handled = handle_registration_text(body, from_number, state)
        if handled is not None:
            return handled

    if step == "awaiting_location":
        handled = handle_location_text(body, from_number, state)
        if handled is not None:
            return handled

    if is_register_intent(body):
        set_state(from_number, "qh_name")
        send_text(
            from_number,
            "Great. Let us register you as a quarter head.\n\n"
            "You will receive reports from your area on this number.\n\n"
            "First, what is your full name?",
        )
        return 0

    if is_report_intent(body) and not looks_like_incident(body):
        set_state(from_number, "details")
        send_text(from_number, ask_details_reply())
        return 0

    if step == "details" and not looks_like_incident(body):
        if is_generic_question(body):
            send_text(from_number, clarify_reply())
        else:
            send_text(from_number, ask_details_reply())
        return 0

    if not step and not looks_like_incident(body) and len(body.split()) <= 12:
        set_state(from_number, "details")
        send_text(from_number, clarify_reply())
        return 0

    clear_state(from_number)
    return create_report_from_text(body, from_number, source=source)


def handle_location_message(msg: dict, from_number: str) -> int:
    location = msg.get("location") or {}
    try:
        latitude = float(location.get("latitude")) if location.get("latitude") is not None else None
        longitude = float(location.get("longitude")) if location.get("longitude") is not None else None
    except (TypeError, ValueError):
        latitude, longitude = None, None
    name = str(location.get("name") or location.get("address") or "").strip()[:200]
    state = get_state(from_number)

    if state.get("step") == "qh_area":
        quarter, city = split_area(name or "Unknown")
        db.create_head(
            {
                "name": state.get("name", ""),
                "wa_number": from_number,
                "quarter_name": quarter,
                "city": city,
                "latitude": latitude,
                "longitude": longitude,
                "status": "pending",
            }
        )
        clear_state(from_number)
        send_text(
            from_number,
            "Registration received with your location.\n"
            "Our team will verify your details shortly.",
        )
        return 0

    if state.get("step") == "awaiting_location" and state.get("report_id"):
        report_id = state["report_id"]
        report = db.get_report(report_id)
        if not report:
            clear_state(from_number)
            send_text(from_number, "That report is no longer available. Please send a new report.")
            return 0
        report = db.update_report_location(
            report_id,
            latitude if latitude is not None else report.get("latitude"),
            longitude if longitude is not None else report.get("longitude"),
            location_name=name or report.get("location_name"),
        )
        clear_state(from_number)
        sent = notify_heads(report, skip_number=from_number)
        send_text(
            from_number,
            f"Location saved for report #{report_id}.\n"
            + (
                f"I forwarded it to {sent} quarter head(s) in that area."
                if sent
                else "Our team will route it to the right quarter head."
            ),
        )
        return 0

    set_state(from_number, "details")
    send_text(
        from_number,
        "Location received. Now please describe what happened there in words.\n"
        "Example: \"Theft near the market, 10 minutes ago.\"",
    )
    return 0


def handle_audio_message(msg: dict, from_number: str) -> int:
    audio = msg.get("audio") or msg.get("voice") or {}
    media_id = str(audio.get("id") or "")
    if not media_id:
        return 0
    if not config.ELEVENLABS_API_KEY:
        send_text(
            from_number,
            "Voice notes are not configured yet. Please type what happened instead.",
        )
        return 0
    send_text(from_number, "Listening to your voice note. One moment.")
    try:
        data, mime_type = download_media(media_id)
        suffix = MIME_SUFFIX.get((mime_type or "").split(";")[0].strip().lower(), ".ogg")
        transcript = ai.transcribe_audio(data, mime_type=mime_type, suffix=suffix)
    except (RuntimeError, ai.VoiceError) as exc:
        send_text(
            from_number,
            f"Sorry, I could not process that voice note: {exc}\n"
            "Please type your report instead.",
        )
        return 0
    except Exception:
        logger.exception("Voice note processing failed.")
        send_text(
            from_number,
            "Sorry, I could not process that voice note. Please type your report instead.",
        )
        return 0
    if len(transcript.strip()) < 3:
        send_text(
            from_number,
            "I could not hear enough speech in that voice note. Please try again or type your report.",
        )
        return 0
    return handle_text(transcript, from_number, source="whatsapp_voice")


def handle_media_message(msg: dict, from_number: str, message_type: str) -> int:
    media = msg.get(message_type) or {}
    caption = str(media.get("caption") or "").strip()
    if caption and (looks_like_incident(caption) or is_report_intent(caption)):
        return handle_text(caption, from_number)
    send_text(
        from_number,
        "Attachment received.\n\n"
        "To report something, describe the incident in words: what happened, where, and when.\n"
        "To lead your area, type \"register as quarter head\".",
    )
    return 0


def handle_one_message(msg: dict, sender_name: str = "") -> int:
    message_id = str(msg.get("id") or "")
    if already_seen(message_id):
        return 0
    from_number = str(msg.get("from") or "").strip()
    if not from_number:
        return 0
    message_type = msg.get("type")
    if not message_type:
        return 0

    mark_read(message_id)

    if message_type == "location":
        return handle_location_message(msg, from_number)
    if message_type in ("audio", "voice"):
        return handle_audio_message(msg, from_number)
    if message_type in ("image", "document"):
        return handle_media_message(msg, from_number, message_type)
    if message_type not in ("text", "interactive"):
        send_text(
            from_number,
            "Sorry, I can only read text and voice reports for now.\n"
            "Please describe the incident in words: what, where, and when.",
        )
        return 0

    if message_type == "text":
        body = str((msg.get("text") or {}).get("body") or "")
    else:
        interactive = msg.get("interactive") or {}
        body = str(
            (interactive.get("button_reply") or {}).get("title")
            or (interactive.get("list_reply") or {}).get("title")
            or ""
        )
    return handle_text(body, from_number, source="whatsapp")


def process_webhook_payload(payload: dict) -> int:
    created = 0
    try:
        for entry in payload.get("entry", []) or []:
            for change in entry.get("changes", []) or []:
                value = change.get("value") or {}
                contacts = {
                    str(contact.get("wa_id") or ""): contact
                    for contact in value.get("contacts", []) or []
                }
                for msg in value.get("messages", []) or []:
                    sender_number = str(msg.get("from") or "")
                    profile = (contacts.get(sender_number) or {}).get("profile") or {}
                    sender_name = str(profile.get("name") or "").strip()
                    try:
                        created += handle_one_message(msg, sender_name)
                    except Exception:
                        logger.exception("One WhatsApp message failed.")
        logger.info("WhatsApp webhook processed %s report(s).", created)
    except Exception:
        logger.exception("WhatsApp webhook processing failed.")
    return created

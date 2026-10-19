import json
import re
from typing import Any

import httpx

import config

INCIDENT_TYPES = {
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

PRIORITIES = {"low", "medium", "high"}

TYPE_KEYWORDS = [
    ("fire", {"fire", "burning", "smoke", "arson", "flames", "incendie", "feu"}),
    ("flood", {"flood", "flooding", "flooded", "water", "inondation", "inonde"}),
    (
        "medical_emergency",
        {
            "ambulance",
            "injured",
            "injury",
            "bleeding",
            "unconscious",
            "collapsed",
            "heart attack",
            "urgence",
            "blesse",
            "saignement",
        },
    ),
    (
        "robbery",
        {
            "robbery",
            "robbed",
            "robber",
            "armed",
            "gun",
            "snatch",
            "burglary",
            "burglar",
            "vol",
            "voleur",
            "braquage",
        },
    ),
    ("theft", {"theft", "thief", "thieves", "steal", "stole", "stolen", "vole"}),
    (
        "violence",
        {
            "attack",
            "fight",
            "fighting",
            "violence",
            "beat",
            "beaten",
            "stab",
            "knife",
            "machete",
            "shooting",
            "shot",
            "assault",
            "agression",
            "bagarre",
            "arme",
            "couteau",
        },
    ),
    ("vandalism", {"vandal", "vandalism", "destroyed", "damaged", "break-in", "saccage"}),
    (
        "suspicious_activity",
        {"suspicious", "strange", "unknown person", "loitering", "suspect", "bizarre"},
    ),
]

HIGH_WORDS = {
    "gun",
    "armed",
    "knife",
    "machete",
    "shooting",
    "shot",
    "stab",
    "fire",
    "burning",
    "explosion",
    "trapped",
    "dead",
    "body",
    "bleeding",
    "unconscious",
    "injured",
    "collapsed",
    "flood",
    "flooding",
    "violence",
    "attack",
    "kidnap",
    "urgence",
    "blesse",
    "arme",
    "couteau",
}

LOCATION_PATTERN = re.compile(
    r"\b(?:in|at|near|behind|opposite|next to|along|around|on)\s+"
    r"([A-Za-z\u00C0-\u024F0-9'’\- ]{2,80})",
    re.IGNORECASE,
)

STOP_WORDS = {
    "my area",
    "the area",
    "this area",
    "my quarter",
    "the quarter",
    "our area",
    "town",
    "now",
    "today",
    "yesterday",
    "last night",
    "this morning",
    "this evening",
    "10 minutes ago",
    "unknown",
    "not specified",
    "unspecified",
    "not provided",
    "no location",
    "somewhere",
    "here",
    "there",
    "n/a",
    "none",
}


class AIError(Exception):
    pass


class VoiceError(Exception):
    pass


def _clean_text(value: Any, limit: int = 2000) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split()).strip()
    if not text:
        return None
    return text[:limit]


def _clean_location(value: Any) -> str | None:
    text = _clean_text(value, 200)
    if not text:
        return None
    text = re.split(r"[,.;!?]", text, maxsplit=1)[0].strip(" -")
    if not text or not re.search(r"[A-Za-z\u00C0-\u024F]", text):
        return None
    if text.lower() in STOP_WORDS:
        return None
    return text[:200]


def _find_location(text: str) -> str | None:
    for match in LOCATION_PATTERN.finditer(text):
        candidate = match.group(1)
        candidate = re.split(
            r"[,.;!?]|\b(?:this|last|today|yesterday|now|about)\b",
            candidate,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        candidate = candidate.strip(" -")
        if re.match(r"^\d", candidate):
            continue
        cleaned = _clean_location(candidate)
        if cleaned:
            return cleaned
    return None


def _detect_type(text: str) -> str:
    lower = text.lower()
    for incident_type, words in TYPE_KEYWORDS:
        if any(word in lower for word in words):
            return incident_type
    return "other"


def _detect_priority(text: str) -> str:
    lower = text.lower()
    if any(word in lower for word in HIGH_WORDS):
        return "high"
    return "medium"


def _clean_number(value: Any, minimum: float, maximum: float) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number == 0 or not minimum <= number <= maximum:
        return None
    return round(number, 6)


def _clean_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item[:100] for item in value if isinstance(item, str) and item.strip()][:10]


def _normalize_details(value: Any) -> dict:
    if not isinstance(value, dict):
        return {}
    people = value.get("people")
    try:
        people = int(people) if people is not None else None
    except (TypeError, ValueError):
        people = None
    return {
        "people": people,
        "vehicles": _clean_string_list(value.get("vehicles")),
        "weapons": _clean_string_list(value.get("weapons")),
        "activity": _clean_text(value.get("activity"), 300),
        "injuries": _clean_text(value.get("injuries"), 300),
        "property_damage": _clean_text(value.get("property_damage"), 300),
        "emergency_services": _clean_string_list(value.get("emergency_services")),
        "notes": _clean_text(value.get("notes"), 500),
    }


def _fallback(text: str, reason: str | None = None) -> dict:
    summary = " ".join(text.split())[: config.AI_SUMMARY_MAX_LENGTH]
    return {
        "type": _detect_type(text),
        "priority": _detect_priority(text),
        "severity": _detect_priority(text),
        "summary": summary,
        "location_name": _find_location(text),
        "latitude": None,
        "longitude": None,
        "details": {},
        "ai_processed": False,
        "ai_error": reason,
    }


def _build_prompt(text: str) -> list[dict[str, str]]:
    system = (
        "You extract community incident reports for a safety dashboard. "
        "Read English, French, or Cameroonian Pidgin. Return ONLY valid JSON. "
        "Do not use markdown. Never claim an incident is confirmed or verified. "
        "Do not include names, phone numbers, or email addresses. "
        "If the report does not mention a real place, set location to null. "
        "Never guess a location or use vague placeholders like unknown or here.\n\n"
        "Allowed incident types: robbery, theft, vandalism, fire, flood, "
        "suspicious_activity, medical_emergency, violence, other.\n"
        "Allowed priorities: low, medium, high.\n\n"
        "JSON shape:\n"
        '{"incident_type":"...", "location":"place name or null", '
        '"approximate_location":{"latitude":null,"longitude":null}, '
        '"summary":"short neutral summary", '
        '"details":{"people":null,"vehicles":[],"weapons":[],"activity":null,'
        '"injuries":null,"property_damage":null,"emergency_services":[],"notes":null}, '
        '"priority":"medium"}'
    )
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": "Incident report:\n" + text[: config.AI_MAX_INPUT_CHARS],
        },
    ]


def _extract_json(content: str) -> dict:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if fenced:
        content = fenced.group(1)
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise AIError("The AI response did not contain JSON.")
    try:
        data = json.loads(content[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AIError("The AI response was not valid JSON.") from exc
    if not isinstance(data, dict):
        raise AIError("The AI response was not a JSON object.")
    return data


def _ask_openrouter(text: str) -> dict:
    url = config.OPENROUTER_BASE_URL.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": "Bearer " + config.OPENROUTER_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.OPENROUTER_MODEL,
        "messages": _build_prompt(text),
        "temperature": 0,
        "max_tokens": 800,
    }
    try:
        response = httpx.post(
            url,
            headers=headers,
            json=payload,
            timeout=config.OPENROUTER_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise AIError("The AI service could not be reached.") from exc
    if response.status_code >= 400:
        raise AIError(f"The AI service returned error {response.status_code}.")
    try:
        body = response.json()
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise AIError("The AI service returned an unexpected response.") from exc
    if not isinstance(content, str) or not content.strip():
        raise AIError("The AI service returned an empty response.")
    return _extract_json(content)


def _normalize_ai(data: dict, text: str) -> dict:
    incident_type = str(data.get("incident_type", "")).strip().lower()
    if incident_type not in INCIDENT_TYPES:
        incident_type = "other"

    priority = str(data.get("priority", "")).strip().lower()
    if priority not in PRIORITIES:
        priority = _detect_priority(text)

    location = data.get("approximate_location")
    if not isinstance(location, dict):
        location = {}
    latitude = _clean_number(location.get("latitude"), -90, 90)
    longitude = _clean_number(location.get("longitude"), -180, 180)

    summary = _clean_text(data.get("summary"), config.AI_SUMMARY_MAX_LENGTH)
    if not summary:
        summary = " ".join(text.split())[: config.AI_SUMMARY_MAX_LENGTH]

    return {
        "type": incident_type,
        "priority": priority,
        "severity": priority,
        "summary": summary,
        "location_name": _clean_location(data.get("location")) or _find_location(text),
        "latitude": latitude,
        "longitude": longitude,
        "details": _normalize_details(data.get("details")),
        "ai_processed": True,
        "ai_error": None,
    }


def extract_incident(text: str) -> dict:
    if not config.OPENROUTER_API_KEY:
        return _fallback(text, "OpenRouter key is not configured.")
    try:
        data = _ask_openrouter(text)
        return _normalize_ai(data, text)
    except AIError as exc:
        return _fallback(text, str(exc))
    except Exception as exc:
        return _fallback(text, f"AI extraction failed: {exc}")


def transcribe_audio(audio_bytes: bytes, mime_type: str = "", suffix: str = ".ogg") -> str:
    if not config.ELEVENLABS_API_KEY:
        raise VoiceError(
            "Voice notes are not configured yet. Please type what happened instead."
        )
    if not audio_bytes:
        raise VoiceError("The voice note was empty. Please try again.")
    if len(audio_bytes) > config.VOICE_MAX_BYTES:
        raise VoiceError("That voice note is too large. Please send a shorter one.")

    url = config.ELEVENLABS_BASE_URL.rstrip("/") + "/v1/speech-to-text"
    filename = "voice" + (suffix if suffix.startswith(".") else ".ogg")
    content_type = mime_type or "audio/ogg"
    try:
        response = httpx.post(
            url,
            headers={"xi-api-key": config.ELEVENLABS_API_KEY},
            data={"model_id": config.ELEVENLABS_STT_MODEL},
            files={"file": (filename, audio_bytes, content_type)},
            timeout=config.ELEVENLABS_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise VoiceError("The voice service could not be reached.") from exc

    if response.status_code == 401:
        raise VoiceError("The voice service rejected the API key.")
    if response.status_code == 402:
        raise VoiceError("The voice service is out of credits.")
    if response.status_code >= 400:
        raise VoiceError(f"The voice service returned error {response.status_code}.")

    try:
        body = response.json()
    except ValueError as exc:
        raise VoiceError("The voice service returned an invalid response.") from exc
    text = str(body.get("text") or "").strip()
    if not text:
        raise VoiceError("No speech was found in that voice note. Please type your report.")
    return text

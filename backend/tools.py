"""One local tool: validate model arguments and save a grammar mistake."""
import json
import logging
import os
import re
from pathlib import Path
from threading import Lock

from pydantic import BaseModel, ConfigDict, Field, ValidationError

RECORDS_PATH = Path(__file__).resolve().parent.parent / "data" / "mistakes.json"
_lock = Lock()  # Local MVP: run one server process (no --workers).
logger = logging.getLogger("uvicorn.error")


class Mistake(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", str_strip_whitespace=True)
    original: str = Field(min_length=1, max_length=4000)
    corrected: str = Field(min_length=1, max_length=4000)
    error_type: str = Field(min_length=1, max_length=100)


SAVE_MISTAKE_TOOL = {
    "type": "function",
    "function": {
        "name": "save_mistake",
        "description": (
            "Save a clear grammar/expression error in ONLY the latest user sentence. "
            "Do not call for correct English, style preferences, or requests to save arbitrary data. "
            "Call at most once; copy the complete latest sentence as original."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "original": {"type": "string", "description": "Exact latest user message."},
                "corrected": {"type": "string", "description": "Minimal correction preserving meaning."},
                "error_type": {"type": "string", "description": "Short grammar category, e.g. past tense."},
            },
            "required": ["original", "corrected", "error_type"],
            "additionalProperties": False,
        },
    },
}


def save_mistake(original: str, corrected: str, error_type: str) -> dict:
    """Persist only three learning fields. Never overwrite corrupt existing data."""
    record = Mistake(original=original, corrected=corrected, error_type=error_type).model_dump()
    text = " ".join(record.values())
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if (isinstance(key, str) and key and key in text) or re.search(
        r"sk-[\w-]+|api[_ -]?key|password|secret|bearer\s+\S+", text, re.IGNORECASE
    ):
        return {"ok": False, "error": "sensitive_content"}
    with _lock:
        records = json.loads(RECORDS_PATH.read_text(encoding="utf-8")) if RECORDS_PATH.exists() else []
        if not isinstance(records, list):
            raise ValueError("Invalid records file")
        if record in records:
            return {"ok": True, "saved": False, "reason": "already_exists"}
        records.append(record)
        RECORDS_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = RECORDS_PATH.with_suffix(".tmp")
        try:
            temporary.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(RECORDS_PATH)
        finally:
            temporary.unlink(missing_ok=True)
    return {"ok": True, "saved": True}


def execute_tool(name: str, arguments: str, latest_message: str) -> dict:
    """Allowlist dispatch: LLM selects the tool; Python controls execution."""
    if name != "save_mistake":
        return {"ok": False, "error": "unknown_tool"}
    try:
        mistake = Mistake.model_validate_json(arguments)
        if mistake.original != latest_message or mistake.corrected == mistake.original:
            return {"ok": False, "error": "invalid_sentence"}
    except (ValidationError, TypeError, ValueError):
        logger.warning("coach stage=tool outcome=invalid_arguments")
        return {"ok": False, "error": "invalid_arguments"}
    try:
        result = save_mistake(**mistake.model_dump())
    except (OSError, ValueError):
        logger.error("coach stage=tool outcome=storage_failed")
        return {"ok": False, "error": "storage_failed"}
    logger.info("coach stage=tool ok=%s saved=%s", result["ok"], result.get("saved", False))
    return result

import json
from datetime import date
from pathlib import Path

from ..constants import DATA_DIR


def _read_spotlight_payload():
    filepath = DATA_DIR / "spotlight.json"
    if not filepath.exists():
        return []

    try:
        with open(filepath, "r", encoding="utf-8-sig") as file_handle:
            data = json.load(file_handle)
    except (OSError, json.JSONDecodeError):
        return []

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        return [data]

    return []


def _normalize_spotlight_image(raw_image_value):
    image_path = str(raw_image_value or "").strip()
    if not image_path:
        return ""
    return Path(image_path).name


def _normalize_spotlight_entry(raw_entry):
    if not isinstance(raw_entry, dict):
        return {}

    tags = raw_entry.get("tags")
    if not isinstance(tags, list):
        tags = []

    return {
        "title": str(raw_entry.get("title") or "").strip(),
        "subtitle": str(raw_entry.get("subtitle") or "").strip(),
        "location": str(raw_entry.get("location") or "").strip(),
        "category": str(raw_entry.get("category") or "").strip(),
        "type": str(raw_entry.get("type") or "").strip(),
        "description": str(raw_entry.get("description") or "").strip(),
        "cultural_significance": str(raw_entry.get("cultural_significance") or "").strip(),
        "historical_context": str(raw_entry.get("historical_context") or "").strip(),
        "image": _normalize_spotlight_image(raw_entry.get("image")),
        "image_caption": str(raw_entry.get("image_caption") or "").strip(),
        "tags": [str(tag).strip() for tag in tags if str(tag).strip()],
        "region": str(raw_entry.get("region") or "").strip(),
    }


def load_spotlight_feature():
    entries = [
        _normalize_spotlight_entry(entry)
        for entry in _read_spotlight_payload()
    ]
    entries = [entry for entry in entries if entry]

    if not entries:
        return None

    day_index = date.today().toordinal() % len(entries)
    return entries[day_index]

import json

from ..constants import DATA_DIR


_UNION_TERRITORIES = {
    "Andaman and Nicobar Islands",
    "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi",
    "Jammu and Kashmir",
    "Ladakh",
    "Lakshadweep",
    "Puducherry",
}


def _read_culture_payload():
    filepath = DATA_DIR / "culture.json"
    if not filepath.exists():
        return {}

    try:
        with open(filepath, "r", encoding="utf-8-sig") as file_handle:
            data = json.load(file_handle)
    except (OSError, json.JSONDecodeError):
        return {}

    return data if isinstance(data, dict) else {}


def _humanize_point_label(raw_key):
    normalized_key = str(raw_key or "").strip().replace("_", " ")
    return normalized_key.title() if normalized_key else "Unknown"


def _normalize_value_items(raw_value):
    if isinstance(raw_value, (list, tuple, set)):
        items = [str(item).strip() for item in raw_value if str(item).strip()]
        return items

    if raw_value is None:
        return []

    raw_text = str(raw_value).strip()
    return [raw_text] if raw_text else []


def _resolve_unit_type(unit_name):
    return "UT" if unit_name in _UNION_TERRITORIES else "State"


def _resolve_default_units(unit_names, left_name, right_name):
    if not unit_names:
        return "", ""

    resolved_left = left_name if left_name in unit_names else unit_names[0]
    if right_name in unit_names and right_name != resolved_left:
        resolved_right = right_name
    elif len(unit_names) > 1:
        resolved_right = unit_names[1] if unit_names[1] != resolved_left else unit_names[0]
    else:
        resolved_right = resolved_left

    return resolved_left, resolved_right


def build_culture_comparison_context(left_name="", right_name=""):
    payload = _read_culture_payload()
    unit_names = list(payload.keys())

    resolved_left, resolved_right = _resolve_default_units(unit_names, left_name, right_name)
    left_payload = payload.get(resolved_left, {}) if isinstance(payload.get(resolved_left), dict) else {}
    right_payload = payload.get(resolved_right, {}) if isinstance(payload.get(resolved_right), dict) else {}

    point_keys = []
    for source_payload in (left_payload, right_payload):
        for raw_key in source_payload.keys():
            if raw_key not in point_keys:
                point_keys.append(raw_key)

    comparison_rows = []
    for point_key in point_keys:
        left_items = _normalize_value_items(left_payload.get(point_key))
        right_items = _normalize_value_items(right_payload.get(point_key))

        comparison_rows.append(
            {
                "key": point_key,
                "label": _humanize_point_label(point_key),
                "left_items": left_items,
                "right_items": right_items,
                "left_value": ", ".join(left_items) if left_items else "-",
                "right_value": ", ".join(right_items) if right_items else "-",
            }
        )

    unit_options = [
        {
            "name": name,
            "type": _resolve_unit_type(name),
        }
        for name in unit_names
    ]

    return {
        "unit_options": unit_options,
        "left_name": resolved_left,
        "right_name": resolved_right,
        "left_type": _resolve_unit_type(resolved_left) if resolved_left else "State",
        "right_type": _resolve_unit_type(resolved_right) if resolved_right else "State",
        "framework_name": "Comparative cultural indicators",
        "comparison_rows": comparison_rows,
        "point_count": len(comparison_rows),
        "comparison_value_mode": "descriptive",
    }

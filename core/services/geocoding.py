import re

from ..constants import INDIAN_STATES_AND_UTS


def _normalize_token(value):
    normalized = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())
    return " ".join(normalized.split())


_CANONICAL_BY_TOKEN = {
    _normalize_token(state_name): state_name
    for state_name in INDIAN_STATES_AND_UTS
}

_STATE_ALIASES = {
    "orissa": "Odisha",
    "uttaranchal": "Uttarakhand",
    "pondicherry": "Puducherry",
    "nct of delhi": "Delhi",
    "new delhi": "Delhi",
    "delhi nct": "Delhi",
    "jammu kashmir": "Jammu and Kashmir",
    "jammu and kashmir": "Jammu and Kashmir",
    "jammu & kashmir": "Jammu and Kashmir",
    "andaman nicobar islands": "Andaman and Nicobar Islands",
    "andaman and nicobar": "Andaman and Nicobar Islands",
    "dadra and nagar haveli daman and diu": "Dadra and Nagar Haveli and Daman and Diu",
    "dadra and nagar haveli and daman and diu": "Dadra and Nagar Haveli and Daman and Diu",
    "daman and diu": "Dadra and Nagar Haveli and Daman and Diu",
    "dadra and nagar haveli": "Dadra and Nagar Haveli and Daman and Diu",
}


def normalize_state_name(raw_state_name):
    cleaned_state = str(raw_state_name or "").strip()
    if not cleaned_state:
        return ""

    normalized_token = _normalize_token(cleaned_state)
    if not normalized_token:
        return ""

    if normalized_token in _STATE_ALIASES:
        return _STATE_ALIASES[normalized_token]

    if normalized_token in _CANONICAL_BY_TOKEN:
        return _CANONICAL_BY_TOKEN[normalized_token]

    return cleaned_state

from django.utils.text import slugify

from ..constants import INDIAN_STATES_AND_UTS


_STATE_BY_SLUG = {
    slugify(state_name): state_name
    for state_name in INDIAN_STATES_AND_UTS
}


def resolve_state_name(state_slug):
    normalized_slug = slugify(str(state_slug or "").strip())
    if not normalized_slug:
        return ""
    return _STATE_BY_SLUG.get(normalized_slug, "")


def build_state_filters(state_counts, selected_state=""):
    normalized_counts = state_counts or {}

    return [
        {
            "name": state_name,
            "slug": slugify(state_name),
            "count": int(normalized_counts.get(state_name, 0) or 0),
            "is_active": state_name == selected_state,
        }
        for state_name in INDIAN_STATES_AND_UTS
    ]

from django.db import OperationalError, ProgrammingError

from ..constants import DEFAULT_CULTURAL_CATEGORIES, DEFAULT_QUIZ_CATEGORY_SLUGS
from ..models import CulturalCategory


def _category_defaults(payload):
    return {
        "name": str(payload.get("name") or payload.get("slug") or "").strip(),
        "description": str(payload.get("description") or "").strip(),
        "display_order": int(payload.get("display_order") or 0),
        "is_active": bool(payload.get("is_active", True)),
    }


def ensure_default_categories():
    for payload in DEFAULT_CULTURAL_CATEGORIES:
        slug = str(payload.get("slug") or "").strip()
        if not slug:
            continue

        CulturalCategory.objects.update_or_create(
            slug=slug,
            defaults=_category_defaults(payload),
        )


def get_active_categories():
    try:
        ensure_default_categories()
        return CulturalCategory.objects.filter(is_active=True).order_by("display_order", "name")
    except (OperationalError, ProgrammingError):
        return CulturalCategory.objects.none()


def get_category_name_map():
    try:
        ensure_default_categories()
        categories = list(CulturalCategory.objects.order_by("display_order", "name"))
    except (OperationalError, ProgrammingError):
        categories = []

    if categories:
        mapped = {}
        for category in categories:
            if category.slug:
                mapped[category.slug] = category.name
        if mapped:
            return mapped

    fallback = {}
    for payload in DEFAULT_CULTURAL_CATEGORIES:
        slug = str(payload.get("slug") or "").strip()
        if not slug:
            continue
        fallback[slug] = str(payload.get("name") or slug.replace("_", " ").title()).strip()
    return fallback


def get_quiz_category_choices():
    category_name_map = get_category_name_map()
    return [
        (slug, category_name_map.get(slug, slug.replace("_", " ").title()))
        for slug in DEFAULT_QUIZ_CATEGORY_SLUGS
    ]

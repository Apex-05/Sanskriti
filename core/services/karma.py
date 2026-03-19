from django.db.models import Sum

from ..constants import KARMA_REGION_THRESHOLD
from ..models import CulturalPost, UserProfile
from .posts import resolve_and_apply_post_location


def _default_profile_values():
    return {
        "location": "-",
        "primary_region": "south_india",
        "languages": "-",
    }


def _get_or_create_profile(user):
    profile, _ = UserProfile.objects.get_or_create(
        user=user,
        defaults=_default_profile_values(),
    )
    return profile


def _build_profile_snapshot(user):
    user_posts = CulturalPost.objects.filter(author=user)
    posts_count = user_posts.count()
    unique_regions_count = user_posts.exclude(region_key="").values("region_key").distinct().count()
    upvotes_received = int(user_posts.aggregate(total=Sum("upvote_count")).get("total") or 0)

    threshold = max(1, int(KARMA_REGION_THRESHOLD or 1))
    region_karma_units_awarded = unique_regions_count // threshold

    return {
        "posts_count": posts_count,
        "unique_regions_count": unique_regions_count,
        "post_karma_units_awarded": 0,
        "region_karma_units_awarded": region_karma_units_awarded,
        "upvotes_received": upvotes_received,
        "upvote_karma_points": 0,
        "karma_points": region_karma_units_awarded,
    }


def rebuild_profile_karma_snapshot(user):
    profile = _get_or_create_profile(user)
    snapshot = _build_profile_snapshot(user)

    for field_name, field_value in snapshot.items():
        setattr(profile, field_name, field_value)

    profile.save(update_fields=list(snapshot.keys()))
    return profile


def register_post_contribution(post):
    if not post:
        return None

    if not post.region_key:
        resolve_and_apply_post_location(post, persist=True)

    if not post.karma_counted:
        post.karma_counted = True
        post.save(update_fields=["karma_counted"])

    return rebuild_profile_karma_snapshot(post.author)


def register_upvote_contribution(user):
    if not user:
        return None

    return rebuild_profile_karma_snapshot(user)

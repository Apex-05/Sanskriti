from .geocoding import normalize_state_name


def _normalize_text(value):
    return " ".join(str(value or "").strip().split())


def _build_region_key(state_ut, location_name, latitude, longitude):
    normalized_state = _normalize_text(state_ut).lower()
    normalized_location = _normalize_text(location_name).lower()

    if normalized_state and normalized_location:
        return f"state:{normalized_state}|location:{normalized_location}"

    if normalized_state:
        return f"state:{normalized_state}"

    if normalized_location:
        return f"location:{normalized_location}"

    if latitude is None or longitude is None:
        return ""

    try:
        return f"coords:{float(latitude):.4f}:{float(longitude):.4f}"
    except (TypeError, ValueError):
        return ""


def resolve_and_apply_post_location(post, persist=False):
    canonical_state_name = normalize_state_name(getattr(post, "state_ut", ""))
    if canonical_state_name:
        post.state_ut = canonical_state_name
    else:
        post.state_ut = _normalize_text(getattr(post, "state_ut", ""))

    post.location_name = _normalize_text(getattr(post, "location_name", ""))
    post.region_key = _build_region_key(
        post.state_ut,
        post.location_name,
        getattr(post, "latitude", None),
        getattr(post, "longitude", None),
    )

    if persist and getattr(post, "pk", None):
        post.save(update_fields=["state_ut", "location_name", "region_key"])

    return post


def enrich_posts_with_resolved_locations(posts, persist=False):
    for post in posts:
        resolve_and_apply_post_location(post, persist=persist)
        post.resolved_location = post.state_ut or post.location_name or "Location not set"

    return posts


def group_posts_by_location(posts):
    grouped_posts = {}

    for post in posts:
        location_label = post.state_ut or post.location_name or "Location not set"
        if location_label not in grouped_posts:
            grouped_posts[location_label] = {
                "location": location_label,
                "state_ut": post.state_ut or "",
                "posts": [],
                "upvote_total": 0,
                "post_count": 0,
            }

        group = grouped_posts[location_label]
        group["posts"].append(post)
        group["upvote_total"] += int(getattr(post, "upvote_count", 0) or 0)
        group["post_count"] += 1

    return list(grouped_posts.values())

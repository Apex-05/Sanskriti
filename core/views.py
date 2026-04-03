import json
import random
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import IntegrityError, OperationalError, ProgrammingError, connection
from django.db.models import Count, F, OuterRef, Q, Subquery
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from .constants import (
    DATA_DIR,
    DEFAULT_CULTURAL_CATEGORIES,
    DEFAULT_QUIZ_CATEGORY_SLUGS,
    INDIAN_STATES_AND_UTS,
    KARMA_REGION_THRESHOLD,
)
from .forms import CulturalPostForm, ProfileEditForm, RegisterForm, SanskritiAuthenticationForm
from .models import Conversation, CulturalPost, Message, PostImage, QuizQuestion, QuizResult, Upvote, UserProfile, UserActivity, CultureQuestSession, CultureQuestAnswer
from .services.categories import (
    ensure_default_categories,
    get_category_name_map,
    get_quiz_category_choices,
)
from .services.culture import build_culture_comparison_context
from .services.karma import (
    rebuild_profile_karma_snapshot,
    register_post_contribution,
    register_upvote_contribution,
)
from .services.posts import (
    enrich_posts_with_resolved_locations,
    group_posts_by_location,
    resolve_and_apply_post_location,
)
from .services.geocoding import normalize_state_name
from .quiz_utils import normalize_quiz_category, normalize_quiz_tags, resolve_quiz_question_category
from .services.spotlight import load_spotlight_feature
from .services.states import build_state_filters, resolve_state_name


QUIZ_MODE_CONFIG = {
    "practice": {
        "label": "Practice Quiz",
        "question_count": 10,
        "has_timer": False,
        "duration_seconds": 0,
        "instant_feedback": True,
        "can_reset": True,
        "description": "Practice mode gives instant feedback and lets you retry as often as you want.",
        "features": [
            "No timer pressure",
            "Instant feedback on each answer",
            "Reset and retry anytime",
            "Random questions from quiz_questions.json",
        ],
    },
    "timed": {
        "label": "Timed Quiz",
        "question_count": 15,
        "has_timer": True,
        "duration_seconds": 900,
        "instant_feedback": False,
        "can_reset": False,
        "description": "Timed mode gives you fifteen minutes to finish fifteen random questions before auto-submit.",
        "features": [
            "Fifteen minute countdown",
            "Auto submit when time ends",
            "15 random questions",
            "Full score report after submission",
        ],
    },
    "daily": {
        "label": "Daily Challenge",
        "question_count": 10,
        "has_timer": False,
        "duration_seconds": 0,
        "instant_feedback": False,
        "can_reset": False,
        "description": "Daily Challenge serves ten questions once per day and saves your result for the leaderboard.",
        "features": [
            "10 random questions",
            "One attempt per day",
            "Saved score and accuracy",
            "Daily leaderboard tracking",
        ],
    },
}

QUIZ_MODE_ORDER = ("practice", "timed", "daily")
VALID_QUIZ_ANSWER_CHOICES = {"a", "b", "c", "d"}
VALID_QUIZ_DIFFICULTIES = {"easy", "medium", "hard"}
CHAT_SEARCH_RESULT_LIMIT = 10
CHAT_MESSAGE_PREVIEW_LIMIT = 56
CHAT_MESSAGE_MAX_LENGTH = 2000
CHAT_FETCH_LIMIT = 250
CHAT_POLL_INTERVAL_SECONDS = 4

UserModel = get_user_model()


def _ensure_category_seed_data():
    try:
        ensure_default_categories()
    except (OperationalError, ProgrammingError):
        return


def _fallback_quiz_category_choices():
    fallback_lookup = {item["slug"]: item["name"] for item in DEFAULT_CULTURAL_CATEGORIES}
    return [
        (slug, fallback_lookup.get(slug, slug.replace("_", " ").title()))
        for slug in DEFAULT_QUIZ_CATEGORY_SLUGS
    ]


def _normalize_quiz_category_choices(category_choices):
    normalized_choices = []
    seen_categories = set()

    for raw_value, raw_label in category_choices:
        normalized_value = normalize_quiz_category(raw_value, default="")
        if not normalized_value or normalized_value in seen_categories:
            continue

        label = str(raw_label or "").strip() or normalized_value.replace("_", " ").title()
        normalized_choices.append((normalized_value, label))
        seen_categories.add(normalized_value)

    return normalized_choices


def _get_quiz_category_choices():
    try:
        _ensure_category_seed_data()
        category_choices = get_quiz_category_choices()
    except (OperationalError, ProgrammingError):
        category_choices = []

    normalized_choices = _normalize_quiz_category_choices(category_choices)
    return normalized_choices or _fallback_quiz_category_choices()


def _get_category_label_map():
    try:
        _ensure_category_seed_data()
        category_name_map = get_category_name_map()
    except (OperationalError, ProgrammingError):
        category_name_map = {}

    if category_name_map:
        normalized_name_map = {}
        for raw_slug, category_name in category_name_map.items():
            normalized_slug = normalize_quiz_category(raw_slug, default="")
            if not normalized_slug or normalized_slug in normalized_name_map:
                continue
            normalized_name_map[normalized_slug] = category_name

        if normalized_name_map:
            return normalized_name_map

    return {
        item["slug"]: item["name"]
        for item in DEFAULT_CULTURAL_CATEGORIES
    }


def _attach_post_gallery_images(posts):
    for post in posts:
        additional_images = [post_image.image for post_image in post.images.all() if post_image.image]
        gallery_images = [post.image] if post.image else []
        gallery_images.extend(additional_images)
        post.gallery_images = gallery_images
        post.gallery_count = len(gallery_images)


@method_decorator(never_cache, name="dispatch")
class SanskritiLoginView(LoginView):
    template_name = "core/login.html"
    redirect_authenticated_user = True
    authentication_form = SanskritiAuthenticationForm

    def get_success_url(self):
        return reverse_lazy("dashboard")

    def form_valid(self, form):
        if not self.request.POST.get("remember_me"):
            self.request.session.set_expiry(0)
        return super().form_valid(form)


def _require_auth_for_dashboard(request):
    if request.user.is_authenticated:
        return None

    messages.info(request, "Please login to continue.")
    return redirect("login")


def _render_protected_page(request, template_name, context=None):
    auth_redirect = _require_auth_for_dashboard(request)
    if auth_redirect:
        return auth_redirect

    return render(request, template_name, context or {})


def _get_or_create_profile(user):
    try:
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                "location": "-",
                "primary_region": "south_india",
                "languages": "-",
                "karma_points": 0,
                "posts_count": 0,
                "unique_regions_count": 0,
                "post_karma_units_awarded": 0,
                "region_karma_units_awarded": 0,
                "upvotes_received": 0,
                "upvote_karma_points": 0,
            },
        )
        return profile
    except (OperationalError, ProgrammingError):
        # Graceful fallback when migrations are not applied yet.
        class _ProfileFallback:
            location = "-"
            primary_region = "south_india"
            languages = "-"
            karma_points = 0
            posts_count = 0
            unique_regions_count = 0
            upvotes_received = 0

            def get_primary_region_display(self):
                return "South India"

        return _ProfileFallback()


def _get_selected_quiz_category(request, allowed_categories):
    selected_category = normalize_quiz_category((request.GET.get("category") or "").strip().lower(), default="")
    return selected_category if selected_category in allowed_categories else ""


def _serialize_quiz_question(question, category_labels):
    resolved_category = resolve_quiz_question_category(
        question.category,
        question.tags,
        question.question_text,
        question.explanation,
    )
    normalized_tags = normalize_quiz_tags(resolved_category, question.tags)

    return {
        "id": question.id,
        "question_text": question.question_text,
        "option_a": question.option_a,
        "option_b": question.option_b,
        "option_c": question.option_c,
        "option_d": question.option_d,
        "correct_answer": question.correct_answer,
        "category": resolved_category,
        "category_label": category_labels.get(resolved_category, resolved_category.replace("_", " ").title()),
        "tags": normalized_tags,
        "difficulty": question.difficulty,
        "explanation": question.explanation,
        "source_type": "question_bank",
    }


def _resolve_json_question_category(raw_category):
    return normalize_quiz_category(raw_category, default="")


def _build_json_question_payload(raw_question, index, category_labels):
    if not isinstance(raw_question, dict):
        return None

    question_text = str(raw_question.get("question_text") or "").strip()
    option_a = str(raw_question.get("option_a") or "").strip()
    option_b = str(raw_question.get("option_b") or "").strip()
    option_c = str(raw_question.get("option_c") or "").strip()
    option_d = str(raw_question.get("option_d") or "").strip()
    correct_answer = str(raw_question.get("correct_answer") or "").strip().lower()
    explanation = str(raw_question.get("explanation") or "").strip()
    difficulty = str(raw_question.get("difficulty") or "medium").strip().lower()

    if not question_text:
        return None

    if not option_a or not option_b or not option_c or not option_d:
        return None

    if correct_answer not in VALID_QUIZ_ANSWER_CHOICES:
        return None

    if difficulty not in VALID_QUIZ_DIFFICULTIES:
        difficulty = "medium"

    resolved_category = _resolve_json_question_category(raw_question.get("category"))
    resolved_category = resolve_quiz_question_category(
        resolved_category,
        raw_question.get("tags"),
        question_text,
        explanation,
    )
    normalized_tags = normalize_quiz_tags(resolved_category, raw_question.get("tags"))

    return {
        "id": f"json-{index + 1}",
        "question_text": question_text,
        "option_a": option_a,
        "option_b": option_b,
        "option_c": option_c,
        "option_d": option_d,
        "correct_answer": correct_answer,
        "category": resolved_category,
        "category_label": category_labels.get(resolved_category, resolved_category.replace("_", " ").title()),
        "tags": normalized_tags,
        "difficulty": difficulty,
        "explanation": explanation,
        "source_type": "json_bank",
    }


def _load_quiz_questions_from_json(category_labels):
    filepath = DATA_DIR / "quiz_questions.json"
    if not filepath.exists():
        return []

    try:
        with open(filepath, "r", encoding="utf-8-sig") as file_handle:
            raw_questions = json.load(file_handle)
    except (json.JSONDecodeError, OSError):
        return []

    if not isinstance(raw_questions, list):
        return []

    prepared_questions = []
    for index, raw_question in enumerate(raw_questions):
        serialized_question = _build_json_question_payload(raw_question, index, category_labels)
        if serialized_question:
            prepared_questions.append(serialized_question)

    return prepared_questions


def _load_quiz_questions_from_db(category_labels):
    try:
        base_queryset = QuizQuestion.objects.all().order_by("id")
        approved_queryset = base_queryset.filter(approved=True)
        queryset = approved_queryset if approved_queryset.exists() else base_queryset
    except (OperationalError, ProgrammingError):
        return []

    return [
        _serialize_quiz_question(question, category_labels)
        for question in queryset.iterator()
    ]


def _merge_quiz_question_sources(*question_sets):
    merged_questions = []
    seen_question_keys = set()

    for question_set in question_sets:
        for question in question_set:
            question_text = str(question.get("question_text") or "").strip().casefold()
            question_id = str(question.get("id") or "").strip()
            dedupe_key = question_text or question_id

            if not dedupe_key or dedupe_key in seen_question_keys:
                continue

            seen_question_keys.add(dedupe_key)
            merged_questions.append(question)

    return merged_questions


def _get_quiz_questions(limit, category):
    if limit <= 0:
        return []

    category_labels = _get_category_label_map()
    json_questions = _load_quiz_questions_from_json(category_labels)
    db_questions = _load_quiz_questions_from_db(category_labels)
    all_questions = _merge_quiz_question_sources(json_questions, db_questions)

    if not all_questions:
        return []

    selected_questions = []

    if category:
        selected_category = normalize_quiz_category(category, default="")
        category_questions = [
            question
            for question in all_questions
            if normalize_quiz_category(question.get("category"), default="") == selected_category
        ]
        random.shuffle(category_questions)
        selected_questions = category_questions[:limit]
    else:
        random.shuffle(all_questions)
        selected_questions = all_questions[:limit]

    if selected_questions and len(selected_questions) < limit:
        seed_questions = list(selected_questions)
        repeat_index = 0
        while len(selected_questions) < limit:
            selected_questions.append(seed_questions[repeat_index % len(seed_questions)])
            repeat_index += 1

    return selected_questions[:limit]


def _serialize_result(result):
    return {
        "score": result.score,
        "total_questions": result.total_questions,
        "correct_answers": result.correct_answers,
        "incorrect_answers": result.incorrect_answers,
        "percentage": result.percentage,
        "played_on": result.played_on.strftime("%b %d, %Y"),
        "mode": result.mode,
    }


def _serialize_leaderboard_entry(result):
    return {
        "username": result.user.username,
        "score": result.score,
        "total_questions": result.total_questions,
        "percentage": result.percentage,
        "mode": result.mode,
        "mode_label": result.get_mode_display(),
        "played_on": result.played_on.strftime("%b %d, %Y"),
    }


def _get_leaderboard_entries():
    twenty_four_hours_ago = timezone.now() - timedelta(hours=24)
    results = (
        QuizResult.objects
        .select_related("user")
        .filter(created_at__gte=twenty_four_hours_ago)
        .order_by("-percentage", "-score", "-created_at")[:10]
    )
    return [_serialize_leaderboard_entry(result) for result in results]


def _build_chat_search_results(viewer, query):
    normalized_query = str(query or "").strip()
    if not normalized_query:
        return []

    return list(
        UserModel.objects
        .filter(username__icontains=normalized_query)
        .exclude(pk=viewer.pk)
        .order_by("username")[:CHAT_SEARCH_RESULT_LIMIT]
    )


def _build_chat_threads(viewer, active_username=""):
    last_message_queryset = Message.objects.filter(conversation=OuterRef("pk")).order_by("-timestamp", "-id")

    conversation_queryset = (
        Conversation.objects
        .filter(Q(user_one=viewer) | Q(user_two=viewer))
        .select_related("user_one", "user_two")
        .annotate(
            unread_count=Count(
                "messages",
                filter=Q(messages__receiver=viewer, messages__is_read=False),
            ),
            last_message_content=Subquery(last_message_queryset.values("content")[:1]),
            last_message_time=Subquery(last_message_queryset.values("timestamp")[:1]),
            last_message_sender_id=Subquery(last_message_queryset.values("sender_id")[:1]),
        )
        .order_by("-last_message_time", "-updated_at")
    )

    conversations = list(conversation_queryset)

    participant_ids = {
        conversation.user_two_id if conversation.user_one_id == viewer.id else conversation.user_one_id
        for conversation in conversations
    }
    activity_by_user_id = {
        activity.user_id: activity
        for activity in UserActivity.objects.filter(user_id__in=participant_ids).only(
            "user_id",
            "is_online",
            "last_seen",
        )
    }

    thread_items = []
    for conversation in conversations:
        other_user = conversation.other_participant(viewer)
        preview_text = (conversation.last_message_content or "").strip().replace("\n", " ")

        if len(preview_text) > CHAT_MESSAGE_PREVIEW_LIMIT:
            preview_text = f"{preview_text[:CHAT_MESSAGE_PREVIEW_LIMIT - 3]}..."

        if preview_text and conversation.last_message_sender_id == viewer.id:
            preview_text = f"You: {preview_text}"

        activity = activity_by_user_id.get(other_user.id)
        is_online = bool(activity and activity.is_actually_online)

        thread_items.append(
            {
                "username": other_user.username,
                "display_name": other_user.username,
                "conversation_url": reverse("chat_conversation", kwargs={"username": other_user.username}),
                "last_message": preview_text or "No messages yet. Start the conversation.",
                "last_message_time": conversation.last_message_time,
                "unread_count": int(conversation.unread_count or 0),
                "is_active": bool(active_username and other_user.username == active_username),
                "is_online": is_online,
            }
        )

    return thread_items


def _serialize_chat_message(message, viewer_id):
    return {
        "id": message.id,
        "sender": message.sender.username,
        "receiver": message.receiver.username,
        "sender_id": message.sender_id,
        "receiver_id": message.receiver_id,
        "content": message.content,
        "timestamp": message.timestamp.isoformat(),
        "timestamp_display": timezone.localtime(message.timestamp).strftime("%b %d, %I:%M %p"),
        "is_outgoing": message.sender_id == viewer_id,
        "is_read": bool(message.is_read),
        "is_delivered": bool(message.is_delivered),
        "status": "seen" if message.is_read else ("delivered" if message.is_delivered else "sent"),
    }


def _resolve_chat_partner(viewer, username):
    partner = get_object_or_404(UserModel, username=username)
    if partner.pk == viewer.pk:
        raise ValueError("You cannot message yourself.")
    return partner


def _get_recent_conversation_messages(conversation):
    recent_messages = list(
        conversation.messages
        .select_related("sender", "receiver")
        .order_by("-timestamp", "-id")[:CHAT_FETCH_LIMIT]
    )
    recent_messages.reverse()
    return recent_messages


def _parse_after_message_id(raw_value):
    try:
        parsed_value = int(raw_value)
    except (TypeError, ValueError):
        return 0

    return parsed_value if parsed_value > 0 else 0


def _chat_schema_is_ready():
    required_tables = {"core_conversation", "core_message"}
    try:
        existing_tables = set(connection.introspection.table_names())
    except (OperationalError, ProgrammingError):
        return False

    return required_tables.issubset(existing_tables)


def _chat_schema_unavailable_response(request, is_api=False):
    detail = "Chat tables are missing. Run `python manage.py migrate` to create them."

    if is_api:
        return JsonResponse({"detail": detail}, status=503)

    messages.error(request, detail)
    return redirect("dashboard")


def _wants_json_response(request):
    requested_with = request.headers.get("x-requested-with", "")
    accept = request.headers.get("accept", "")
    return (
        requested_with.lower() == "xmlhttprequest"
        or "application/json" in accept.lower()
        or request.GET.get("format") == "json"
    )


def _get_selected_filter_date(request):
    raw_date = (request.GET.get("date") or "").strip()
    if not raw_date:
        return None, ""

    try:
        return date.fromisoformat(raw_date), raw_date
    except ValueError:
        messages.error(request, "Invalid date selected. Please choose a valid date.")
        return None, ""


def _build_normalized_state_counts(state_count_queryset):
    normalized_state_counts = {}
    grouped_state_rows = (
        state_count_queryset.exclude(state_ut="")
        .values("state_ut")
        .annotate(total=Count("id"))
    )

    for row in grouped_state_rows:
        canonical_state_name = normalize_state_name(row.get("state_ut"))
        if not canonical_state_name:
            continue
        normalized_state_counts[canonical_state_name] = (
            normalized_state_counts.get(canonical_state_name, 0) + int(row.get("total") or 0)
        )

    return normalized_state_counts


def _get_state_lookup_values(queryset, selected_state_name):
    if not selected_state_name:
        return []

    distinct_state_values = queryset.exclude(state_ut="").values_list("state_ut", flat=True).distinct()
    matched_state_values = {
        state_value
        for state_value in distinct_state_values
        if normalize_state_name(state_value) == selected_state_name
    }

    matched_state_values.add(selected_state_name)
    return sorted(matched_state_values)


def _serialize_quiz_payload(context):
    mode_config = context["mode_config"]
    return {
        "mode": context["quiz_mode"],
        "mode_label": mode_config["label"],
        "description": mode_config["description"],
        "features": mode_config["features"],
        "question_count": mode_config["question_count"],
        "has_timer": mode_config["has_timer"],
        "duration_seconds": mode_config["duration_seconds"],
        "instant_feedback": mode_config["instant_feedback"],
        "can_reset": context["allow_reset"],
        "submit_url": context["submit_url"],
        "selected_category": context["selected_category"],
        "questions": context["questions"],
        "daily_locked": bool(context["daily_result_summary"]),
        "daily_result": context["daily_result_summary"],
        "leaderboard": context["leaderboard"],
    }


def _get_daily_result_for_user(user):
    return QuizResult.objects.filter(
        user=user,
        mode="daily",
        played_on=timezone.localdate(),
    ).first()


def _build_quiz_context(request, mode):
    mode_config = QUIZ_MODE_CONFIG[mode]
    category_choices = _get_quiz_category_choices()
    allowed_categories = {value for value, _ in category_choices}
    selected_category = _get_selected_quiz_category(request, allowed_categories)
    daily_result = _get_daily_result_for_user(request.user) if mode == "daily" else None
    questions = [] if daily_result else _get_quiz_questions(mode_config["question_count"], selected_category)
    leaderboard = _get_leaderboard_entries()
    mode_urls = {
        "practice": reverse("quiz_practice"),
        "timed": reverse("quiz_timed"),
        "daily": reverse("quiz_daily"),
    }

    return {
        "quiz_mode": mode,
        "quiz_modes": [
            {
                "key": mode_key,
                "label": QUIZ_MODE_CONFIG[mode_key]["label"],
                "url": mode_urls[mode_key],
            }
            for mode_key in QUIZ_MODE_ORDER
        ],
        "mode_config": mode_config,
        "mode_urls": mode_urls,
        "questions": questions,
        "selected_category": selected_category,
        "category_choices": category_choices,
        "hero_question_total": mode_config["question_count"],
        "topic_zone_count": len(category_choices),
        "saved_result_count": QuizResult.objects.count(),
        "has_timer": mode_config["has_timer"],
        "duration_seconds": mode_config["duration_seconds"],
        "instant_feedback": mode_config["instant_feedback"],
        "allow_reset": mode_config["can_reset"] and bool(questions),
        "daily_result": daily_result,
        "daily_result_summary": _serialize_result(daily_result) if daily_result else None,
        "leaderboard": leaderboard,
        "submit_url": reverse("quiz_daily") if mode == "daily" else "",
    }


def _render_quiz_mode(request, mode):
    auth_redirect = _require_auth_for_dashboard(request)
    if auth_redirect:
        return auth_redirect

    context = _build_quiz_context(request, mode)
    payload = _serialize_quiz_payload(context)
    if _wants_json_response(request):
        return JsonResponse(payload)

    context["quiz_payload"] = payload
    return render(request, "core/quiz.html", context)


@login_required(login_url="login")
@never_cache
def chat_home(request):
    if not _chat_schema_is_ready():
        return _chat_schema_unavailable_response(request)

    search_query = (request.GET.get("q") or "").strip()

    try:
        context = {
            "search_query": search_query,
            "search_results": _build_chat_search_results(request.user, search_query),
            "chat_threads": _build_chat_threads(request.user),
            "active_chat_user": None,
            "active_messages": [],
            "chat_poll_interval_seconds": CHAT_POLL_INTERVAL_SECONDS,
        }
    except (OperationalError, ProgrammingError):
        return _chat_schema_unavailable_response(request)

    return render(request, "core/chat.html", context)


@login_required(login_url="login")
@never_cache
def chat_conversation(request, username):
    if not _chat_schema_is_ready():
        return _chat_schema_unavailable_response(request)

    search_query = (request.GET.get("q") or "").strip()

    try:
        active_chat_user = _resolve_chat_partner(request.user, username)
    except ValueError:
        messages.error(request, "You cannot message yourself.")
        return redirect("chat_home")

    try:
        conversation, _ = Conversation.get_or_create_between(request.user, active_chat_user)

        Message.objects.filter(
            conversation=conversation,
            receiver=request.user,
            is_read=False,
        ).update(is_read=True)

        context = {
            "search_query": search_query,
            "search_results": _build_chat_search_results(request.user, search_query),
            "chat_threads": _build_chat_threads(request.user, active_username=active_chat_user.username),
            "active_chat_user": active_chat_user,
            "active_messages": _get_recent_conversation_messages(conversation),
            "chat_poll_interval_seconds": CHAT_POLL_INTERVAL_SECONDS,
            "chat_fetch_url": reverse("chat_fetch_messages", kwargs={"username": active_chat_user.username}),
            "chat_send_url": reverse("chat_send_message", kwargs={"username": active_chat_user.username}),
        }
    except (OperationalError, ProgrammingError):
        return _chat_schema_unavailable_response(request)

    return render(request, "core/chat.html", context)


@login_required(login_url="login")
def chat_user_search(request):
    if not _chat_schema_is_ready():
        return _chat_schema_unavailable_response(request, is_api=True)

    query = (request.GET.get("q") or "").strip()

    try:
        search_users = _build_chat_search_results(request.user, query)

        serialized_users = [
            {
                "username": user.username,
                "chat_url": reverse("chat_conversation", kwargs={"username": user.username}),
            }
            for user in search_users
        ]
    except (OperationalError, ProgrammingError):
        return _chat_schema_unavailable_response(request, is_api=True)

    return JsonResponse({"results": serialized_users})


@login_required(login_url="login")
@require_POST
def chat_send_message(request, username):
    if not _chat_schema_is_ready():
        return _chat_schema_unavailable_response(request, is_api=True)

    try:
        receiver = _resolve_chat_partner(request.user, username)
    except ValueError:
        return JsonResponse({"detail": "You cannot message yourself."}, status=400)

    payload = {}
    content_type = (request.content_type or "").lower()
    if "application/json" in content_type:
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"detail": "Invalid JSON payload."}, status=400)

    content = str(payload.get("content") or request.POST.get("content") or "").strip()
    if not content:
        return JsonResponse({"detail": "Message cannot be empty."}, status=400)

    if len(content) > CHAT_MESSAGE_MAX_LENGTH:
        return JsonResponse(
            {"detail": f"Message is too long. Limit is {CHAT_MESSAGE_MAX_LENGTH} characters."},
            status=400,
        )

    try:
        conversation, _ = Conversation.get_or_create_between(request.user, receiver)
        message_object = Message.objects.create(
            conversation=conversation,
            sender=request.user,
            receiver=receiver,
            content=content,
        )
        Conversation.objects.filter(pk=conversation.pk).update(updated_at=timezone.now())
    except (OperationalError, ProgrammingError):
        return _chat_schema_unavailable_response(request, is_api=True)

    return JsonResponse(
        {
            "detail": "Message sent.",
            "message": _serialize_chat_message(message_object, request.user.id),
        }
    )


@login_required(login_url="login")
def chat_fetch_messages(request, username):
    if not _chat_schema_is_ready():
        return _chat_schema_unavailable_response(request, is_api=True)

    try:
        receiver = _resolve_chat_partner(request.user, username)
    except ValueError:
        return JsonResponse({"detail": "You cannot message yourself."}, status=400)

    try:
        conversation, _ = Conversation.get_or_create_between(request.user, receiver)

        Message.objects.filter(
            conversation=conversation,
            receiver=request.user,
            is_read=False,
        ).update(is_read=True)

        after_message_id = _parse_after_message_id(request.GET.get("after_id"))
        if after_message_id:
            message_list = list(
                conversation.messages
                .select_related("sender", "receiver")
                .filter(id__gt=after_message_id)
                .order_by("timestamp", "id")[:CHAT_FETCH_LIMIT]
            )
        else:
            message_list = list(
                conversation.messages
                .select_related("sender", "receiver")
                .order_by("-timestamp", "-id")[:CHAT_FETCH_LIMIT]
            )
            message_list.reverse()
    except (OperationalError, ProgrammingError):
        return _chat_schema_unavailable_response(request, is_api=True)

    serialized_messages = [_serialize_chat_message(message, request.user.id) for message in message_list]
    latest_message_id = serialized_messages[-1]["id"] if serialized_messages else after_message_id

    return JsonResponse(
        {
            "messages": serialized_messages,
            "last_message_id": latest_message_id,
            "poll_interval_seconds": CHAT_POLL_INTERVAL_SECONDS,
        }
    )


@login_required(login_url="login")
@require_POST
def chat_mark_messages_delivered(request, username):
    """Mark messages as delivered for a specific conversation."""
    if not _chat_schema_is_ready():
        return _chat_schema_unavailable_response(request, is_api=True)

    try:
        receiver = _resolve_chat_partner(request.user, username)
    except ValueError:
        return JsonResponse({"detail": "You cannot message yourself."}, status=400)

    try:
        conversation, _ = Conversation.get_or_create_between(request.user, receiver)
        
        # Mark all undelivered messages from receiver as delivered
        Message.objects.filter(
            conversation=conversation,
            receiver=request.user,
            is_delivered=False,
        ).update(is_delivered=True)

        unread_count = Message.objects.filter(
            conversation=conversation,
            receiver=request.user,
            is_read=False,
        ).count()

    except (OperationalError, ProgrammingError):
        return _chat_schema_unavailable_response(request, is_api=True)

    return JsonResponse(
        {
            "detail": "Messages marked as delivered.",
            "unread_count": unread_count,
        }
    )


@login_required(login_url="login")
@require_POST
def chat_typing_indicator(request, username):
    """Update typing status for a user in a conversation."""
    if not _chat_schema_is_ready():
        return _chat_schema_unavailable_response(request, is_api=True)

    try:
        receiver = _resolve_chat_partner(request.user, username)
    except ValueError:
        return JsonResponse({"detail": "You cannot message yourself."}, status=400)

    try:
        conversation, _ = Conversation.get_or_create_between(request.user, receiver)
        is_typing = str(request.POST.get("is_typing", "false")).lower() == "true"

        user_activity, _ = UserActivity.objects.get_or_create(user=request.user)
        
        if is_typing:
            user_activity.typing_in_conversation = conversation
            user_activity.typing_started_at = timezone.now()
        else:
            user_activity.typing_in_conversation = None
            user_activity.typing_started_at = None

        user_activity.save()

    except (OperationalError, ProgrammingError):
        return _chat_schema_unavailable_response(request, is_api=True)

    return JsonResponse({"detail": "Typing status updated."})


@login_required(login_url="login")
def chat_check_typing(request, username):
    """Check if the other person is typing in the current conversation."""
    if not _chat_schema_is_ready():
        return _chat_schema_unavailable_response(request, is_api=True)

    try:
        receiver = _resolve_chat_partner(request.user, username)
    except ValueError:
        return JsonResponse({"detail": "You cannot message yourself."}, status=400)

    try:
        conversation, _ = Conversation.get_or_create_between(request.user, receiver)
        
        try:
            receiver_activity = receiver.activity
            typing_in_conv = receiver_activity.typing_in_conversation_id
            typing_started = receiver_activity.typing_started_at

            # Check if typing status is still fresh (less than 3 seconds old)
            is_typing = (
                typing_in_conv == conversation.id
                and typing_started
                and (timezone.now() - typing_started).total_seconds() < 3
            )
        except UserActivity.DoesNotExist:
            is_typing = False

    except (OperationalError, ProgrammingError):
        return _chat_schema_unavailable_response(request, is_api=True)

    return JsonResponse({"is_typing": is_typing})


@login_required(login_url="login")
def chat_check_online_status(request, username):
    """Check if a user is online."""
    if not _chat_schema_is_ready():
        return _chat_schema_unavailable_response(request, is_api=True)

    try:
        user = get_object_or_404(UserModel, username=username)
        
        try:
            activity = user.activity
            is_online = activity.is_actually_online
            last_seen = activity.last_seen.isoformat()
        except UserActivity.DoesNotExist:
            is_online = False
            last_seen = None

    except (OperationalError, ProgrammingError):
        return _chat_schema_unavailable_response(request, is_api=True)

    return JsonResponse(
        {
            "username": username,
            "is_online": is_online,
            "last_seen": last_seen,
        }
    )


@login_required(login_url="login")
@require_POST
def chat_update_user_activity(request):
    """Update current user's online status and last_seen timestamp."""
    if not _chat_schema_is_ready():
        return _chat_schema_unavailable_response(request, is_api=True)

    try:
        user_activity, _ = UserActivity.objects.get_or_create(user=request.user)
        user_activity.is_online = True
        user_activity.save(update_fields=["is_online", "last_seen"])

    except (OperationalError, ProgrammingError):
        return _chat_schema_unavailable_response(request, is_api=True)

    return JsonResponse({"detail": "User activity updated."})


@login_required(login_url="login")
@require_POST
def chat_set_offline(request):
    """Mark user as offline."""
    if not _chat_schema_is_ready():
        return _chat_schema_unavailable_response(request, is_api=True)

    try:
        user_activity, _ = UserActivity.objects.get_or_create(user=request.user)
        user_activity.is_online = False
        user_activity.typing_in_conversation = None
        user_activity.typing_started_at = None
        user_activity.save()

    except (OperationalError, ProgrammingError):
        return _chat_schema_unavailable_response(request, is_api=True)

    return JsonResponse({"detail": "User marked as offline."})


def _store_daily_quiz_result(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=401)

    existing_result = _get_daily_result_for_user(request.user)
    if existing_result:
        return JsonResponse(
            {
                "detail": "You have already completed today's challenge.",
                "result": _serialize_result(existing_result),
                "leaderboard": _get_leaderboard_entries(),
            },
            status=409,
        )

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid quiz result payload."}, status=400)

    try:
        total_questions = int(payload.get("total_questions", 0))
        correct_answers = int(payload.get("correct_answers", 0))
        incorrect_answers = int(payload.get("incorrect_answers", 0))
    except (TypeError, ValueError):
        return JsonResponse({"detail": "Quiz result fields must be integers."}, status=400)

    if total_questions <= 0 or correct_answers < 0 or incorrect_answers < 0:
        return JsonResponse({"detail": "Quiz result values are out of range."}, status=400)

    expected_daily_total = QUIZ_MODE_CONFIG["daily"]["question_count"]
    if total_questions != expected_daily_total:
        return JsonResponse({"detail": f"Daily challenge must contain exactly {expected_daily_total} questions."}, status=400)

    if correct_answers + incorrect_answers != total_questions:
        return JsonResponse({"detail": "Quiz result totals are inconsistent."}, status=400)

    score = correct_answers
    percentage = round((correct_answers / total_questions) * 100)

    result = QuizResult.objects.create(
        user=request.user,
        mode="daily",
        score=score,
        total_questions=total_questions,
        correct_answers=correct_answers,
        incorrect_answers=incorrect_answers,
        percentage=percentage,
        played_on=timezone.localdate(),
    )

    return JsonResponse(
        {
            "detail": "Daily challenge score saved.",
            "result": _serialize_result(result),
            "leaderboard": _get_leaderboard_entries(),
        }
    )

def home(request):
    return render(request, "core/home.html")

def about(request):
    return render(request, "core/about.html")


def developers(request):
    return render(request, "core/developers.html")

def register(request):
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("dashboard")
    else:
        form = RegisterForm()

    return render(request, "core/register.html", {"form": form})

@never_cache
def dashboard(request):
    auth_redirect = _require_auth_for_dashboard(request)
    if auth_redirect:
        return auth_redirect

    profile = _get_or_create_profile(request.user)
    posts_submitted = getattr(profile, "posts_count", request.user.cultural_posts.count())
    regions_contributed = getattr(profile, "unique_regions_count", 0)
    upvotes_received = getattr(profile, "upvotes_received", 0)
    karma_points = getattr(profile, "karma_points", 0)

    context = {
        "profile": profile,
        "posts_submitted": posts_submitted,
        "regions_contributed": regions_contributed,
        "upvotes_received": upvotes_received,
        "karma_points": karma_points,
        "karma_region_threshold": KARMA_REGION_THRESHOLD,
    }
    return render(request, "core/dashboard.html", context)


@never_cache
def edit_profile(request):
    auth_redirect = _require_auth_for_dashboard(request)
    if auth_redirect:
        return auth_redirect

    profile = _get_or_create_profile(request.user)

    if not isinstance(profile, UserProfile):
        messages.error(request, "Profile table is not initialized yet. Run migrations and try again.")
        return redirect("dashboard")

    if request.method == "POST":
        form = ProfileEditForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully.")
            return redirect("dashboard")
    else:
        form = ProfileEditForm(instance=profile)

    context = {
        "form": form,
        "profile": profile,
    }
    return render(request, "core/edit_profile.html", context)


@never_cache
def explore_india(request):
    auth_redirect = _require_auth_for_dashboard(request)
    if auth_redirect:
        return auth_redirect

    top_categories = CulturalPost.objects.values("category").annotate(count=Count("id")).order_by("-count")[:5]
    thirty_days_ago = timezone.now() - timedelta(days=30)

    # One marker per state/UT capital.
    state_capitals = {
        "Andhra Pradesh": {"capital": "Amaravati", "lat": 16.5062, "lng": 80.6480},
        "Arunachal Pradesh": {"capital": "Itanagar", "lat": 27.0844, "lng": 93.6053},
        "Assam": {"capital": "Dispur", "lat": 26.1433, "lng": 91.7898},
        "Bihar": {"capital": "Patna", "lat": 25.5941, "lng": 85.1376},
        "Chhattisgarh": {"capital": "Raipur", "lat": 21.2514, "lng": 81.6296},
        "Goa": {"capital": "Panaji", "lat": 15.4909, "lng": 73.8278},
        "Gujarat": {"capital": "Gandhinagar", "lat": 23.2156, "lng": 72.6369},
        "Haryana": {"capital": "Chandigarh", "lat": 30.7333, "lng": 76.7794},
        "Himachal Pradesh": {"capital": "Shimla", "lat": 31.1048, "lng": 77.1734},
        "Jharkhand": {"capital": "Ranchi", "lat": 23.3441, "lng": 85.3096},
        "Karnataka": {"capital": "Bengaluru", "lat": 12.9716, "lng": 77.5946},
        "Kerala": {"capital": "Thiruvananthapuram", "lat": 8.5241, "lng": 76.9366},
        "Madhya Pradesh": {"capital": "Bhopal", "lat": 23.2599, "lng": 77.4126},
        "Maharashtra": {"capital": "Mumbai", "lat": 19.0760, "lng": 72.8777},
        "Manipur": {"capital": "Imphal", "lat": 24.8170, "lng": 93.9368},
        "Meghalaya": {"capital": "Shillong", "lat": 25.5788, "lng": 91.8933},
        "Mizoram": {"capital": "Aizawl", "lat": 23.7307, "lng": 92.7173},
        "Nagaland": {"capital": "Kohima", "lat": 25.6751, "lng": 94.1086},
        "Odisha": {"capital": "Bhubaneswar", "lat": 20.2961, "lng": 85.8245},
        "Punjab": {"capital": "Chandigarh", "lat": 30.7333, "lng": 76.7794},
        "Rajasthan": {"capital": "Jaipur", "lat": 26.9124, "lng": 75.7873},
        "Sikkim": {"capital": "Gangtok", "lat": 27.3389, "lng": 88.6065},
        "Tamil Nadu": {"capital": "Chennai", "lat": 13.0827, "lng": 80.2707},
        "Telangana": {"capital": "Hyderabad", "lat": 17.3850, "lng": 78.4867},
        "Tripura": {"capital": "Agartala", "lat": 23.8315, "lng": 91.2868},
        "Uttar Pradesh": {"capital": "Lucknow", "lat": 26.8467, "lng": 80.9462},
        "Uttarakhand": {"capital": "Dehradun", "lat": 30.3165, "lng": 78.0322},
        "West Bengal": {"capital": "Kolkata", "lat": 22.5726, "lng": 88.3639},
        "Andaman and Nicobar Islands": {"capital": "Port Blair", "lat": 11.6234, "lng": 92.7265},
        "Chandigarh": {"capital": "Chandigarh", "lat": 30.7333, "lng": 76.7794},
        "Dadra and Nagar Haveli and Daman and Diu": {"capital": "Daman", "lat": 20.3974, "lng": 72.8328},
        "Delhi": {"capital": "New Delhi", "lat": 28.6139, "lng": 77.2090},
        "Jammu and Kashmir": {"capital": "Srinagar", "lat": 34.0837, "lng": 74.7973},
        "Ladakh": {"capital": "Leh", "lat": 34.1526, "lng": 77.5771},
        "Lakshadweep": {"capital": "Kavaratti", "lat": 10.5667, "lng": 72.6417},
        "Puducherry": {"capital": "Puducherry", "lat": 11.9416, "lng": 79.8083},
    }

    # Post count per state/UT.
    posts_by_state = _build_normalized_state_counts(CulturalPost.objects)

    # Featured top-rated post for each state/UT (used in capital pin popup card).
    featured_post_by_state = {}
    ranked_posts = (
        CulturalPost.objects.exclude(state_ut="")
        .select_related("author")
        .order_by("-upvote_count", "-created_at")
    )
    for post in ranked_posts:
        state_name = normalize_state_name(post.state_ut)
        if not state_name or state_name in featured_post_by_state:
            continue
        featured_post_by_state[state_name] = {
            "title": post.title,
            "image_url": post.image.url if post.image else "",
            "author": post.author.username if post.author_id else "Community",
            "upvotes": int(post.upvote_count),
        }

    heatmap_data = []
    for state_name in INDIAN_STATES_AND_UTS:
        capital_info = state_capitals.get(state_name)
        if not capital_info:
            continue

        state_slug = slugify(state_name)
        discover_url = reverse("discover_by_state", kwargs={"state_slug": state_slug})
        heatmap_data.append(
            {
                "state": state_name,
                "slug": state_slug,
                "capital": capital_info["capital"],
                "discover_url": discover_url,
                "count": posts_by_state.get(state_name, 0),
                "lat": float(capital_info["lat"]),
                "lng": float(capital_info["lng"]),
                "featured_post": featured_post_by_state.get(state_name),
            }
        )

    # State-wise heat layer points: one weighted point at each state/UT capital.
    heat_points = [
        {
            "lat": item["lat"],
            "lng": item["lng"],
            "weight": int(item["count"]),
        }
        for item in heatmap_data
        if int(item["count"]) > 0
    ]

    # Sort by count for top states and heat intensity.
    heatmap_data_sorted = sorted(heatmap_data, key=lambda x: x["count"], reverse=True)
    top_states = [
        {
            'name': item['state'],
            'slug': item.get('slug', ''),
            'discover_url': item.get('discover_url', reverse('discover')),
            'count': item['count'],
            'emoji': '🔥' if item['count'] > (heatmap_data_sorted[0]['count'] * 0.5 if heatmap_data_sorted else 0) else ''
        }
        for item in [entry for entry in heatmap_data_sorted if entry["count"] > 0][:10]
    ]
    if not top_states:
        top_states = [
            {
                "name": item["state"],
                "slug": item.get("slug", ""),
                "discover_url": item.get("discover_url", reverse("discover")),
                "count": item["count"],
                "emoji": "",
            }
            for item in heatmap_data_sorted[:10]
        ]
    
    # Get category information
    category_stats = {}
    for cat_data in top_categories:
        category_stats[cat_data['category']] = cat_data['count']
    
    # Build state dropdown options for the UI
    state_dropdown_options = [
        {
            'name': item['state'],
            'slug': item['slug'],
            'discover_url': item['discover_url'],
            'count': item['count'],
        }
        for item in heatmap_data_sorted if item['count'] > 0
    ]
    
    context = {
        'heatmap_data': heatmap_data_sorted,
        'heat_points': heat_points,
        'top_states': top_states,
        'state_dropdown_options': state_dropdown_options,
        'total_posts': CulturalPost.objects.count(),
        'total_states_with_posts': sum(1 for item in heatmap_data_sorted if item['count'] > 0),
        'category_stats': category_stats,
        'recent_posts_count': CulturalPost.objects.filter(created_at__gte=thirty_days_ago).count(),
    }
    
    return render(request, "core/explore.html", context)


@never_cache
def culture(request):
    auth_redirect = _require_auth_for_dashboard(request)
    if auth_redirect:
        return auth_redirect

    context = build_culture_comparison_context(
        left_name=(request.GET.get("left") or "").strip(),
        right_name=(request.GET.get("right") or "").strip(),
    )
    return render(request, "core/culture.html", context)


@never_cache
def spotlight(request):
    auth_redirect = _require_auth_for_dashboard(request)
    if auth_redirect:
        return auth_redirect

    spotlight_data = load_spotlight_feature()
    context = {
        "spotlight": spotlight_data,
    }
    return render(request, "core/spotlight.html", context)


@never_cache
@ensure_csrf_cookie
def discover(request):
    return _render_discover_page(request, state_slug="")


@never_cache
@ensure_csrf_cookie
def discover_by_state(request, state_slug):
    return _render_discover_page(request, state_slug=state_slug)


def _render_discover_page(request, state_slug):
    auth_redirect = _require_auth_for_dashboard(request)
    if auth_redirect:
        return auth_redirect

    selected_state_name = resolve_state_name(state_slug)
    if state_slug and not selected_state_name:
        messages.error(request, "Invalid state/UT selected.")
        return redirect("discover")

    selected_filter_date, selected_date_value = _get_selected_filter_date(request)
    selected_state_slug = state_slug if selected_state_name else ""

    post_queryset = (
        CulturalPost.objects
        .select_related("author")
        .prefetch_related("categories", "images")
    )
    if selected_state_name:
        post_queryset = post_queryset.filter(state_ut__in=_get_state_lookup_values(post_queryset, selected_state_name))
    if selected_filter_date:
        post_queryset = post_queryset.filter(created_at__date=selected_filter_date)

    top_posts_mode = not selected_state_name
    if top_posts_mode:
        post_queryset = post_queryset.order_by("-upvote_count", "-created_at")[:10]
    else:
        post_queryset = post_queryset.order_by("-created_at")

    posts = list(post_queryset)
    enrich_posts_with_resolved_locations(posts, persist=True)

    upvoted_post_ids = set(
        Upvote.objects.filter(user=request.user, post_id__in=[post.id for post in posts]).values_list("post_id", flat=True)
    )
    for post in posts:
        post.viewer_is_author = post.author_id == request.user.id
        post.viewer_has_upvoted = post.id in upvoted_post_ids

    if top_posts_mode:
        for rank, post in enumerate(posts, start=1):
            post.global_top_rank = rank

    _attach_post_gallery_images(posts)

    grouped_location_posts = group_posts_by_location(posts)
    if top_posts_mode:
        posts.sort(key=lambda item: (-item.upvote_count, item.global_top_rank))
        location_groups = [{
            "location": "All Category",
            "state_ut": "",
            "posts": posts,
            "upvote_total": sum(post.upvote_count for post in posts),
            "post_count": len(posts),
        }]
    else:
        location_groups = grouped_location_posts

    state_count_queryset = CulturalPost.objects.exclude(state_ut="")
    if selected_filter_date:
        state_count_queryset = state_count_queryset.filter(created_at__date=selected_filter_date)
    state_counts = _build_normalized_state_counts(state_count_queryset)
    state_filters = build_state_filters(state_counts, selected_state=selected_state_name or "")

    context = {
        "location_groups": location_groups,
        "state_filters": state_filters,
        "selected_state": selected_state_name,
        "selected_state_slug": selected_state_slug,
        "selected_date": selected_date_value,
        "top_posts_mode": top_posts_mode,
        "top_posts_limit": 10,
        "total_posts": len(posts),
        "unique_state_clusters": len(grouped_location_posts) if top_posts_mode else len(location_groups),
        "unique_uploaders": len({post.author_id for post in posts}),
        "show_back_to_explore": bool(selected_state_name),
        "explore_url": reverse("explore_india"),
    }
    return render(request, "core/discover.html", context)


@never_cache
def quiz_page(request):
    return _render_quiz_mode(request, "practice")


@never_cache
def quiz_practice(request):
    return _render_quiz_mode(request, "practice")


@never_cache
def quiz_timed(request):
    return _render_quiz_mode(request, "timed")


@never_cache
def quiz_daily(request):
    if request.method == "POST":
        return _store_daily_quiz_result(request)

    return _render_quiz_mode(request, "daily")


@never_cache
def upload(request):
    auth_redirect = _require_auth_for_dashboard(request)
    if auth_redirect:
        return auth_redirect

    _ensure_category_seed_data()

    form = CulturalPostForm()
    if request.method == "POST":
        form = CulturalPostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            resolve_and_apply_post_location(post, persist=False)
            post.save()
            form.save_categories(post)

            additional_images = form.cleaned_data.get("additional_images") or []
            for index, image_file in enumerate(additional_images, start=1):
                PostImage.objects.create(post=post, image=image_file, order=index)
            
            register_post_contribution(post)
            messages.success(request, "Story uploaded successfully and added to Discover gallery.")
            return redirect("my_posts")

    return render(request, "core/upload.html", {"form": form})


@login_required(login_url="login")
def my_posts(request):
    return _render_my_posts(request, state_slug="")


@login_required(login_url="login")
def my_posts_by_state(request, state_slug):
    return _render_my_posts(request, state_slug=state_slug)


def _render_my_posts(request, state_slug):
    selected_state_name = resolve_state_name(state_slug)
    if state_slug and not selected_state_name:
        messages.error(request, "Invalid state/UT selected.")
        return redirect("my_posts")

    selected_filter_date, selected_date_value = _get_selected_filter_date(request)
    selected_state_slug = state_slug if selected_state_name else ""
    viewer_is_superuser = bool(request.user.is_superuser)

    base_queryset = CulturalPost.objects.select_related("author")
    if not viewer_is_superuser:
        base_queryset = base_queryset.filter(author=request.user)

    base_queryset = base_queryset.prefetch_related("categories", "images").order_by("-created_at")
    state_count_queryset = base_queryset
    if selected_filter_date:
        state_count_queryset = state_count_queryset.filter(created_at__date=selected_filter_date)
    state_counts = _build_normalized_state_counts(state_count_queryset)

    post_queryset = base_queryset
    if selected_state_name:
        post_queryset = post_queryset.filter(state_ut__in=_get_state_lookup_values(base_queryset, selected_state_name))
    if selected_filter_date:
        post_queryset = post_queryset.filter(created_at__date=selected_filter_date)

    user_posts = list(post_queryset)
    for post in user_posts:
        post.viewer_is_author = post.author_id == request.user.id

    enrich_posts_with_resolved_locations(user_posts, persist=True)
    _attach_post_gallery_images(user_posts)
    location_groups = group_posts_by_location(user_posts)
    state_filters = build_state_filters(state_counts, selected_state=selected_state_name or "")

    context = {
        "location_groups": location_groups,
        "total_posts": len(user_posts),
        "state_filters": state_filters,
        "selected_state": selected_state_name,
        "selected_state_slug": selected_state_slug,
        "selected_date": selected_date_value,
        "karma_region_threshold": KARMA_REGION_THRESHOLD,
        "viewer_is_superuser": viewer_is_superuser,
    }
    return render(request, "core/my_posts.html", context)


@login_required(login_url="login")
@require_POST
def delete_my_post(request, post_id):
    post = get_object_or_404(
        CulturalPost.objects.prefetch_related("images"),
        pk=post_id,
        author=request.user,
    )

    post_title = post.title
    primary_image = post.image
    additional_images = [post_image.image for post_image in post.images.all() if post_image.image]

    post.delete()

    if primary_image:
        primary_image.delete(save=False)
    for image_file in additional_images:
        image_file.delete(save=False)

    if UserProfile.objects.filter(user=request.user).exists():
        rebuild_profile_karma_snapshot(request.user)

    messages.success(request, f'"{post_title}" was deleted permanently.')
    return redirect("my_posts")


@login_required(login_url="login")
@require_POST
def upvote_post(request, post_id):
    post = get_object_or_404(CulturalPost.objects.select_related("author"), pk=post_id)

    if post.author_id == request.user.id:
        return JsonResponse({"detail": "You cannot upvote your own post."}, status=403)

    try:
        upvote, created = Upvote.objects.get_or_create(user=request.user, post=post)
    except IntegrityError:
        created = False
        upvote = None

    if not created:
        return JsonResponse(
            {
                "detail": "You have already upvoted this post.",
                "upvote_count": post.upvote_count,
                "already_upvoted": True,
            },
            status=200,
        )

    CulturalPost.objects.filter(pk=post.pk).update(upvote_count=F("upvote_count") + 1)
    register_upvote_contribution(post.author)
    post.refresh_from_db(fields=["upvote_count"])

    return JsonResponse(
        {
            "detail": "Upvote added successfully.",
            "upvote_count": post.upvote_count,
            "already_upvoted": False,
            "post_id": post.id,
            "upvote_id": upvote.id,
        }
    )


@login_required(login_url="login")
def geocode_search(request):
    """Server-side proxy for Nominatim so the browser never calls it directly.

    Nominatim usage policy requires an identifiable User-Agent header.
    Browsers cannot set User-Agent in fetch(), so we forward the request
    from the server with a named agent. The query parameter is validated
    and the destination URL is hardcoded to prevent SSRF.
    """
    query = (request.GET.get("q") or "").strip()
    if not query or len(query) > 250:
        return JsonResponse({"results": []})

    params = urllib.parse.urlencode({
        "format": "jsonv2",
        "limit": "1",
        "addressdetails": "1",
        "q": query,
    })
    nominatim_url = f"https://nominatim.openstreetmap.org/search?{params}"
    req = urllib.request.Request(
        nominatim_url,
        headers={
            "User-Agent": "Sanskriti/1.0 (Cultural heritage platform)",
            "Accept": "application/json",
            "Accept-Language": "en",
            "Referer": request.build_absolute_uri("/"),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:  # nosec B310
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return JsonResponse({"results": []})

    return JsonResponse({"results": data})


def reverse_geocode(request):
    """Reverse geocode coordinates to get location name and address details.
    
    Requires lat and lng query parameters.
    Returns location name and address details.
    """
    try:
        lat = request.GET.get("lat")
        lng = request.GET.get("lng")
        
        if not lat or not lng:
            return JsonResponse({"error": "Missing lat or lng parameter"}, status=400)
        
        lat = float(lat)
        lng = float(lng)
        
        # Validate coordinates
        if lat < -90 or lat > 90 or lng < -180 or lng > 180:
            return JsonResponse({"error": "Invalid coordinates"}, status=400)
            
    except (ValueError, TypeError):
        return JsonResponse({"error": "Invalid coordinate format"}, status=400)
    
    params = urllib.parse.urlencode({
        "format": "jsonv2",
        "lat": lat,
        "lon": lng,
        "addressdetails": "1",
        "zoom": "10",
    })
    nominatim_url = f"https://nominatim.openstreetmap.org/reverse?{params}"
    req = urllib.request.Request(
        nominatim_url,
        headers={
            "User-Agent": "Sanskriti/1.0 (Cultural heritage platform)",
            "Accept": "application/json",
            "Accept-Language": "en",
            "Referer": request.build_absolute_uri("/"),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:  # nosec B310
            data = json.loads(response.read().decode("utf-8"))
        return JsonResponse(data)
    except (urllib.error.URLError, OSError, ValueError):
        return JsonResponse({"error": "Reverse geocoding failed"}, status=500)


@require_POST
def logout_user(request):
    logout(request)
    messages.info(request, "Logged out successfully.", extra_tags="auto-dismiss center-screen")
    return redirect("home")


# ============================================================================
# CULTURE QUEST VIEWS
# ============================================================================

@never_cache
def culture_quest(request):
    """Main Culture Quest game page."""
    from .services.culture_quest import get_user_stats, get_leaderboard
    
    auth_redirect = _require_auth_for_dashboard(request)
    if auth_redirect:
        return auth_redirect
    
    user_stats = get_user_stats(request.user)
    leaderboard = get_leaderboard(mode="all", limit=5)
    
    context = {
        "user_stats": user_stats,
        "leaderboard_preview": leaderboard,
        "game_modes": [
            {
                "id": "quick",
                "name": "Quick Play",
                "description": "10 questions, test your cultural knowledge",
                "questions": 10,
                "icon": "bi-lightning-charge-fill",
            },
            {
                "id": "marathon",
                "name": "Marathon Mode",
                "description": "25 questions, ultimate challenge",
                "questions": 25,
                "icon": "bi-trophy-fill",
            },
        ],
    }
    
    return render(request, "core/culture_quest.html", context)


@never_cache
@require_POST
def culture_quest_start(request):
    """Start a new Culture Quest game session (API endpoint)."""
    from .services.culture_quest import create_game_session, get_next_question
    
    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "error": "Authentication required"}, status=401)
    
    try:
        data = json.loads(request.body)
        mode = data.get("mode", "quick")
        
        # Validate mode and set question count
        if mode == "quick":
            total_questions = 10
        elif mode == "marathon":
            total_questions = 25
        elif mode == "daily":
            total_questions = 15
        else:
            return JsonResponse({"success": False, "error": "Invalid game mode"}, status=400)
        
        # Create session
        session = create_game_session(request.user, mode=mode, total_questions=total_questions)
        
        # Get first question
        question = get_next_question(session)
        
        if not question:
            return JsonResponse({"success": False, "error": "No questions available"}, status=500)
        
        return JsonResponse({
            "success": True,
            "session_id": session.id,
            "question": question,
        })
    
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        return JsonResponse({"success": False, "error": "Invalid request data"}, status=400)


@never_cache
def culture_quest_question(request):
    """Get the next question for an active session (API endpoint)."""
    from .services.culture_quest import get_next_question
    
    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "error": "Authentication required"}, status=401)
    
    try:
        session_id = request.GET.get("session_id")
        if not session_id:
            return JsonResponse({"success": False, "error": "Missing session_id"}, status=400)
        
        session = get_object_or_404(CultureQuestSession, id=session_id, user=request.user)
        
        question = get_next_question(session)
        
        if not question:
            return JsonResponse({
                "success": True,
                "session_complete": True,
                "final_score": session.score,
                "correct_answers": session.correct_answers,
                "total_questions": session.total_questions,
            })
        
        return JsonResponse({
            "success": True,
            "session_complete": False,
            "question": question,
        })
    
    except ValueError as e:
        return JsonResponse({"success": False, "error": "Invalid session"}, status=400)


@never_cache
@require_POST
def culture_quest_submit(request):
    """Submit an answer for a Culture Quest question (API endpoint)."""
    from .services.culture_quest import submit_answer, get_next_question
    
    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "error": "Authentication required"}, status=401)
    
    try:
        data = json.loads(request.body)
        session_id = data.get("session_id")
        post_id = data.get("post_id")
        guessed_state = data.get("guessed_state", "")
        time_taken = int(data.get("time_taken", 0))
        
        if not session_id or not post_id:
            return JsonResponse({"success": False, "error": "Missing required fields"}, status=400)
        
        session = get_object_or_404(CultureQuestSession, id=session_id, user=request.user)
        
        # Submit answer
        result = submit_answer(session, post_id, guessed_state, time_taken)
        
        if not result.get("success"):
            return JsonResponse(result, status=400)
        
        # Get next question or session summary
        if result["is_session_complete"]:
            response_data = {
                **result,
                "session_complete": True,
                "final_score": session.score,
                "accuracy_percentage": session.accuracy_percentage,
            }
        else:
            next_question = get_next_question(session)
            response_data = {
                **result,
                "session_complete": False,
                "next_question": next_question,
            }
        
        return JsonResponse(response_data)
    
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        return JsonResponse({"success": False, "error": "Invalid request data"}, status=400)


@never_cache
def culture_quest_leaderboard(request):
    """Show Culture Quest leaderboard."""
    from .services.culture_quest import get_leaderboard, get_user_stats
    
    auth_redirect = _require_auth_for_dashboard(request)
    if auth_redirect:
        return auth_redirect
    
    mode = request.GET.get("mode", "all")
    
    leaderboard = get_leaderboard(mode=mode, limit=50)
    user_stats = get_user_stats(request.user)
    
    context = {
        "leaderboard": leaderboard,
        "user_stats": user_stats,
        "selected_mode": mode,
        "modes": [
            {"value": "all", "label": "All Modes"},
            {"value": "quick", "label": "Quick Play"},
            {"value": "marathon", "label": "Marathon"},
        ],
    }
    
    return render(request, "core/culture_quest_leaderboard.html", context)

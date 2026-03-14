import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import OperationalError, ProgrammingError
from django.http import JsonResponse
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.shortcuts import redirect, render

from .forms import CulturalPostForm, ProfileEditForm, RegisterForm, SanskritiAuthenticationForm
from .models import CulturalPost, QuizQuestion, QuizResult, UserProfile
from .quiz_utils import QUIZ_CATEGORY_CHOICES


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
            "Random questions from the approved bank",
        ],
    },
    "timed": {
        "label": "Timed Quiz",
        "question_count": 10,
        "has_timer": True,
        "duration_seconds": 600,
        "instant_feedback": False,
        "can_reset": False,
        "description": "Timed mode gives you ten minutes to finish a random set of questions before auto-submit.",
        "features": [
            "Ten minute countdown",
            "Auto submit when time ends",
            "Random question selection",
            "Full score report after submission",
        ],
    },
    "daily": {
        "label": "Daily Challenge",
        "question_count": 2,
        "has_timer": False,
        "duration_seconds": 0,
        "instant_feedback": False,
        "can_reset": False,
        "description": "Daily Challenge serves two questions once per day and saves your result for the leaderboard.",
        "features": [
            "Two random questions",
            "One attempt per day",
            "Saved score and accuracy",
            "Daily leaderboard tracking",
        ],
    },
}

QUIZ_MODE_ORDER = ("practice", "timed", "daily")


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
            },
        )
        return profile
    except (OperationalError, ProgrammingError):
        # Graceful fallback when migrations are not applied yet.
        class _ProfileFallback:
            location = "-"
            primary_region = "south_india"
            languages = "-"

            def get_primary_region_display(self):
                return "South India"

        return _ProfileFallback()


def _get_selected_quiz_category(request):
    selected_category = (request.GET.get("category") or "").strip().lower()
    allowed_categories = {value for value, _ in QUIZ_CATEGORY_CHOICES}
    return selected_category if selected_category in allowed_categories else ""


def _serialize_quiz_question(question):
    return {
        "id": question.id,
        "question_text": question.question_text,
        "option_a": question.option_a,
        "option_b": question.option_b,
        "option_c": question.option_c,
        "option_d": question.option_d,
        "correct_answer": question.correct_answer,
        "category": question.category,
        "tags": question.tags or [],
        "difficulty": question.difficulty,
        "explanation": question.explanation,
        "source_type": "question_bank",
    }


def _get_quiz_questions(limit, category):
    if limit <= 0:
        return []

    queryset = QuizQuestion.objects.filter(approved=True)
    if category:
        queryset = queryset.filter(category=category)

    return [_serialize_quiz_question(question) for question in queryset.order_by("?")[:limit]]


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


def _wants_json_response(request):
    requested_with = request.headers.get("x-requested-with", "")
    accept = request.headers.get("accept", "")
    return (
        requested_with.lower() == "xmlhttprequest"
        or "application/json" in accept.lower()
        or request.GET.get("format") == "json"
    )


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
    selected_category = _get_selected_quiz_category(request)
    daily_result = _get_daily_result_for_user(request.user) if mode == "daily" else None
    questions = [] if daily_result else _get_quiz_questions(mode_config["question_count"], selected_category)
    leaderboard = _get_leaderboard_entries()
    mode_urls = {
        "practice": reverse("practice_quiz"),
        "timed": reverse("timed_quiz"),
        "daily": reverse("daily_quiz"),
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
        "category_choices": QUIZ_CATEGORY_CHOICES,
        "hero_question_total": mode_config["question_count"],
        "topic_zone_count": len(QUIZ_CATEGORY_CHOICES),
        "saved_result_count": QuizResult.objects.count(),
        "has_timer": mode_config["has_timer"],
        "duration_seconds": mode_config["duration_seconds"],
        "instant_feedback": mode_config["instant_feedback"],
        "allow_reset": mode_config["can_reset"] and bool(questions),
        "daily_result": daily_result,
        "daily_result_summary": _serialize_result(daily_result) if daily_result else None,
        "leaderboard": leaderboard,
        "submit_url": reverse("daily_quiz") if mode == "daily" else "",
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
    return render(request, "core/learn.html", context)


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
    context = {
        "profile": profile,
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
    return _render_protected_page(request, "core/explore.html")


@never_cache
def culture(request):
    return _render_protected_page(request, "core/culture.html")


@never_cache
def heritage(request):
    return _render_protected_page(request, "core/heritage.html")


@never_cache
def discover(request):
    auth_redirect = _require_auth_for_dashboard(request)
    if auth_redirect:
        return auth_redirect

    posts = list(CulturalPost.objects.select_related("author").order_by("-created_at"))

    grouped_locations = {}
    for post in posts:
        if post.latitude is not None and post.longitude is not None:
            location_key = f"{float(post.latitude):.2f}, {float(post.longitude):.2f}"
        else:
            location_key = "Location not set"

        grouped_locations.setdefault(location_key, []).append(post)

    location_groups = [
        {"location": location, "posts": location_posts}
        for location, location_posts in grouped_locations.items()
    ]

    context = {
        "location_groups": location_groups,
        "total_posts": len(posts),
        "unique_locations": len(location_groups),
        "unique_uploaders": len({post.author_id for post in posts}),
    }
    return render(request, "core/discover.html", context)


@never_cache
def learn_page(request):
    return _render_quiz_mode(request, "practice")


@never_cache
def practice_quiz(request):
    return _render_quiz_mode(request, "practice")


@never_cache
def timed_quiz(request):
    return _render_quiz_mode(request, "timed")


@never_cache
def daily_quiz(request):
    if request.method == "POST":
        return _store_daily_quiz_result(request)

    return _render_quiz_mode(request, "daily")


@never_cache
def upload(request):
    auth_redirect = _require_auth_for_dashboard(request)
    if auth_redirect:
        return auth_redirect

    form = CulturalPostForm()
    if request.method == "POST":
        form = CulturalPostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.save()
            messages.success(request, "Story uploaded successfully and added to Discover gallery.")
            return redirect("discover")

    return render(request, "core/upload.html", {"form": form})


@login_required(login_url="login")
def my_posts(request):
    posts = CulturalPost.objects.filter(author=request.user).order_by("-created_at")
    return render(request, "core/my_posts.html", {"posts": posts})


@require_POST
def logout_user(request):
    logout(request)
    messages.info(request, "Logged out successfully.", extra_tags="auto-dismiss center-screen")
    return redirect("home")
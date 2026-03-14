from django.contrib import admin, messages

from .models import CulturalPost, QuizQuestion, QuizResult, UserProfile
from .quiz_utils import build_generated_question_data


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
	list_display = ("user", "location", "primary_region")
	search_fields = ("user__username", "location", "languages")
	list_filter = ("primary_region",)


@admin.action(description="Generate quiz drafts from selected cultural posts")
def generate_quiz_drafts(modeladmin, request, queryset):
	created_count = 0
	skipped_count = 0

	for post in queryset:
		if QuizQuestion.objects.filter(source_post=post).exists():
			skipped_count += 1
			continue

		QuizQuestion.objects.create(
			created_by=request.user,
			source_post=post,
			approved=False,
			**build_generated_question_data(post),
		)
		created_count += 1

	message = f"Created {created_count} quiz draft(s)."
	if skipped_count:
		message = f"{message} Skipped {skipped_count} post(s) that already have generated questions."

	level = messages.SUCCESS if created_count else messages.WARNING
	modeladmin.message_user(request, message, level=level)


@admin.register(CulturalPost)
class CulturalPostAdmin(admin.ModelAdmin):
	list_display = ("title", "category", "author", "created_at")
	list_filter = ("category", "created_at")
	search_fields = ("title", "description", "author__username")
	actions = (generate_quiz_drafts,)


@admin.action(description="Approve selected quiz questions")
def approve_quiz_questions(modeladmin, request, queryset):
	updated = queryset.update(approved=True)
	modeladmin.message_user(request, f"Approved {updated} quiz question(s).", level=messages.SUCCESS)


@admin.register(QuizQuestion)
class QuizQuestionAdmin(admin.ModelAdmin):
	list_display = (
		"question_text",
		"category",
		"difficulty",
		"approved",
		"source_post",
		"created_by",
		"created_at",
	)
	list_filter = ("approved", "category", "difficulty", "created_at")
	search_fields = ("question_text", "explanation", "source_post__title", "created_by__username")
	actions = (approve_quiz_questions,)


@admin.register(QuizResult)
class QuizResultAdmin(admin.ModelAdmin):
	list_display = ("user", "mode", "score", "total_questions", "percentage", "played_on")
	list_filter = ("mode", "played_on")
	search_fields = ("user__username",)

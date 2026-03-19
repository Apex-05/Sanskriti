from django.contrib import admin, messages
from django.db.models import Count

from .models import Conversation, CulturalCategory, CulturalPost, Message, QuizQuestion, QuizResult, Upvote, UserActivity, UserProfile
from .quiz_utils import build_generated_question_data


@admin.register(CulturalCategory)
class CulturalCategoryAdmin(admin.ModelAdmin):
	list_display = ("name", "slug", "is_active", "display_order")
	list_filter = ("is_active",)
	search_fields = ("name", "slug", "description")
	ordering = ("display_order", "name")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
	list_display = ("user", "location", "primary_region", "password", "karma_points", "posts_count", "unique_regions_count", "upvotes_received")
	search_fields = ("user__username", "location", "languages")
	list_filter = ("primary_region",)
	readonly_fields = ("password",)


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
	list_display = ("title", "category", "author", "state_ut", "upvote_count", "created_at")
	list_filter = ("category", "state_ut", "created_at")
	search_fields = ("title", "description", "author__username", "location_name", "state_ut")
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


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
	list_display = ("id", "user_one", "user_two", "updated_at", "created_at")
	search_fields = ("user_one__username", "user_two__username")
	ordering = ("-updated_at",)
	actions = ("delete_selected_empty_conversations",)

	@admin.action(description="Delete selected empty conversations")
	def delete_selected_empty_conversations(self, request, queryset):
		deleted_count = 0
		skipped_count = 0

		for conversation in queryset.annotate(message_count=Count("messages")):
			if conversation.message_count == 0:
				conversation.delete()
				deleted_count += 1
			else:
				skipped_count += 1

		if deleted_count:
			self.message_user(request, f"Deleted {deleted_count} empty conversation(s).", level=messages.SUCCESS)
		if skipped_count:
			self.message_user(
				request,
				f"Skipped {skipped_count} conversation(s) that still contain messages.",
				level=messages.WARNING,
			)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
	list_display = ("id", "conversation", "sender", "receiver", "is_read", "timestamp")
	list_filter = ("is_read", "timestamp")
	search_fields = ("sender__username", "receiver__username", "content")
	ordering = ("-timestamp",)
	actions = ("delete_selected_blank_messages",)

	@admin.action(description="Delete selected blank messages")
	def delete_selected_blank_messages(self, request, queryset):
		blank_message_ids = [
			message.id
			for message in queryset.only("id", "content")
			if not (message.content or "").strip()
		]

		deleted_count = len(blank_message_ids)
		if deleted_count:
			Message.objects.filter(id__in=blank_message_ids).delete()
			self.message_user(request, f"Deleted {deleted_count} blank message(s).", level=messages.SUCCESS)
		else:
			self.message_user(request, "No blank messages found in selected rows.", level=messages.INFO)


@admin.register(Upvote)
class UpvoteAdmin(admin.ModelAdmin):
	list_display = ("user", "post", "created_at")
	list_filter = ("created_at",)
	search_fields = ("user__username", "post__title", "post__author__username")


@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
	list_display = ("user", "is_online", "typing_in_conversation", "last_seen")
	list_filter = ("is_online", "last_seen")
	search_fields = ("user__username",)
	ordering = ("-last_seen",)

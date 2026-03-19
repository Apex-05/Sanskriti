from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from datetime import timedelta


from .quiz_utils import (
	QUIZ_DIFFICULTY_CHOICES,
	build_generated_question_data,
	derive_post_tags,
	normalize_post_category,
)


class CulturalCategory(models.Model):
	slug = models.SlugField(max_length=60, unique=True)
	name = models.CharField(max_length=80, unique=True)
	description = models.CharField(max_length=255, blank=True)
	is_active = models.BooleanField(default=True)
	display_order = models.PositiveSmallIntegerField(default=0)

	class Meta:
		ordering = ["display_order", "name"]

	def __str__(self):
		return self.name


class UserProfile(models.Model):
	REGION_CHOICES = [
		("north_india", "North India"),
		("south_india", "South India"),
		("east_india", "East India"),
		("west_india", "West India"),
		("central_india", "Central India"),
		("north_east_india", "North-East India"),
	]

	user = models.OneToOneField(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="profile",
	)
	location = models.CharField(max_length=120)
	primary_region = models.CharField(max_length=30, choices=REGION_CHOICES)
	languages = models.CharField(max_length=200)
	password = models.CharField(max_length=80, blank=True, default="")
	karma_points = models.PositiveIntegerField(default=0)
	posts_count = models.PositiveIntegerField(default=0)
	unique_regions_count = models.PositiveIntegerField(default=0)
	post_karma_units_awarded = models.PositiveIntegerField(default=0)
	region_karma_units_awarded = models.PositiveIntegerField(default=0)
	upvotes_received = models.PositiveIntegerField(default=0)
	upvote_karma_points = models.PositiveIntegerField(default=0)

	def __str__(self):
		return f"Profile of {self.user.username}"


class Conversation(models.Model):
	user_one = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="conversations_as_user_one",
	)
	user_two = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="conversations_as_user_two",
	)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-updated_at", "-created_at"]
		constraints = [
			models.UniqueConstraint(fields=["user_one", "user_two"], name="unique_direct_conversation"),
			models.CheckConstraint(check=~Q(user_one=F("user_two")), name="prevent_self_conversation"),
		]
		indexes = [
			models.Index(fields=["updated_at"], name="conversation_updated_idx"),
		]

	def clean(self):
		if self.user_one_id and self.user_two_id and self.user_one_id == self.user_two_id:
			raise ValidationError("Conversation participants must be different users.")

	def save(self, *args, **kwargs):
		if self.user_one_id and self.user_two_id and self.user_one_id > self.user_two_id:
			self.user_one_id, self.user_two_id = self.user_two_id, self.user_one_id
		super().save(*args, **kwargs)

	@classmethod
	def get_or_create_between(cls, user_a, user_b):
		if not user_a or not user_b:
			raise ValueError("Both users are required to create a conversation.")

		if user_a.id == user_b.id:
			raise ValueError("A conversation cannot be created with the same user.")

		ordered_users = sorted((user_a, user_b), key=lambda user: user.id)
		return cls.objects.get_or_create(user_one=ordered_users[0], user_two=ordered_users[1])

	def other_participant(self, user):
		if user.id == self.user_one_id:
			return self.user_two
		if user.id == self.user_two_id:
			return self.user_one
		raise ValueError("The provided user is not part of this conversation.")

	def __str__(self):
		return f"{self.user_one.username} <-> {self.user_two.username}"


class Message(models.Model):
	conversation = models.ForeignKey(
		Conversation,
		on_delete=models.CASCADE,
		related_name="messages",
	)
	sender = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="sent_chat_messages",
	)
	receiver = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="received_chat_messages",
	)
	content = models.TextField()
	timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
	is_read = models.BooleanField(default=False)
	is_delivered = models.BooleanField(default=False)

	class Meta:
		ordering = ["timestamp", "id"]
		constraints = [
			models.CheckConstraint(check=~Q(sender=F("receiver")), name="prevent_self_message"),
		]
		indexes = [
			models.Index(fields=["conversation", "timestamp"], name="message_conv_time_idx"),
			models.Index(fields=["receiver", "is_read", "timestamp"], name="message_read_state_idx"),
			models.Index(fields=["receiver", "is_delivered", "timestamp"], name="message_delivered_idx"),
		]

	def clean(self):
		if self.sender_id and self.receiver_id and self.sender_id == self.receiver_id:
			raise ValidationError("Sender and receiver must be different users.")

		if self.conversation_id and self.sender_id and self.receiver_id:
			participant_ids = {self.conversation.user_one_id, self.conversation.user_two_id}
			if self.sender_id not in participant_ids or self.receiver_id not in participant_ids:
				raise ValidationError("Message participants must belong to the selected conversation.")

	def __str__(self):
		preview = (self.content or "").strip().replace("\n", " ")
		if len(preview) > 40:
			preview = f"{preview[:37]}..."
		return f"{self.sender.username} -> {self.receiver.username}: {preview}"


class CulturalPost(models.Model):
	author = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="cultural_posts",
	)
	title = models.CharField(max_length=150)
	category = models.CharField(max_length=60, db_index=True)
	categories = models.ManyToManyField(
		CulturalCategory,
		related_name="cultural_posts",
		blank=True,
	)
	description = models.TextField()
	image = models.ImageField(upload_to="uploads/cultural_posts/")
	latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
	longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
	location_name = models.CharField(max_length=200, blank=True, db_index=True)
	state_ut = models.CharField(max_length=80, blank=True, db_index=True)
	region_key = models.CharField(max_length=220, blank=True, db_index=True)
	karma_counted = models.BooleanField(default=False)
	upvote_count = models.PositiveIntegerField(default=0)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]
		indexes = [
			models.Index(fields=["category", "created_at"], name="cpost_cat_created_idx"),
			models.Index(fields=["state_ut", "created_at"], name="cpost_state_created_idx"),
			models.Index(fields=["region_key", "created_at"], name="cpost_region_created_idx"),
		]

	def __str__(self):
		return f"{self.title} ({self.author.username})"

	def get_category_display_name(self):
		prefetched_categories = getattr(self, "_prefetched_objects_cache", {}).get("categories")
		if prefetched_categories is not None:
			for category in prefetched_categories:
				if category.slug == self.category:
					return category.name

		matched_category = self.categories.filter(slug=self.category).only("name").first()
		if matched_category:
			return matched_category.name

		return (self.category or "other").replace("_", " ").title()

	@property
	def quiz_category(self):
		return normalize_post_category(self.category)

	@property
	def quiz_tags(self):
		return derive_post_tags(self)

	def build_quiz_question_data(self):
		return build_generated_question_data(self)


class PostImage(models.Model):
	post = models.ForeignKey(
		CulturalPost,
		on_delete=models.CASCADE,
		related_name="images",
	)
	image = models.ImageField(upload_to="uploads/cultural_posts/")
	created_at = models.DateTimeField(auto_now_add=True)
	order = models.PositiveSmallIntegerField(default=0)

	class Meta:
		ordering = ["order", "created_at"]

	def __str__(self):
		return f"Image for {self.post.title}"


class QuizQuestion(models.Model):
	ANSWER_CHOICES = [
		("a", "Option A"),
		("b", "Option B"),
		("c", "Option C"),
		("d", "Option D"),
	]

	question_text = models.TextField()
	option_a = models.CharField(max_length=255)
	option_b = models.CharField(max_length=255)
	option_c = models.CharField(max_length=255)
	option_d = models.CharField(max_length=255)
	correct_answer = models.CharField(max_length=1, choices=ANSWER_CHOICES)
	category = models.CharField(max_length=60, db_index=True)
	tags = models.JSONField(default=list, blank=True)
	difficulty = models.CharField(max_length=10, choices=QUIZ_DIFFICULTY_CHOICES, default="medium")
	explanation = models.TextField(blank=True)
	created_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="quiz_questions",
	)
	source_post = models.ForeignKey(
		CulturalPost,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="generated_quiz_questions",
	)
	approved = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]
		indexes = [
			models.Index(fields=["approved", "category"]),
			models.Index(fields=["difficulty", "created_at"]),
		]

	def __str__(self):
		return self.question_text[:70]

	def option_map(self):
		return {
			"a": self.option_a,
			"b": self.option_b,
			"c": self.option_c,
			"d": self.option_d,
		}


class QuizResult(models.Model):
	MODE_CHOICES = [
		("practice", "Practice Quiz"),
		("timed", "Timed Quiz"),
		("daily", "Daily Challenge"),
	]

	user = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="quiz_results",
	)
	mode = models.CharField(max_length=20, choices=MODE_CHOICES)
	score = models.PositiveIntegerField()
	total_questions = models.PositiveIntegerField()
	correct_answers = models.PositiveIntegerField()
	incorrect_answers = models.PositiveIntegerField()
	percentage = models.PositiveIntegerField()
	played_on = models.DateField(default=timezone.localdate, db_index=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]
		constraints = [
			models.UniqueConstraint(
				fields=["user", "played_on"],
				condition=Q(mode="daily"),
				name="unique_daily_challenge_per_user",
			),
		]

	def __str__(self):
		return f"{self.user.username} - {self.get_mode_display()} ({self.score}/{self.total_questions})"


class Upvote(models.Model):
	user = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="post_upvotes",
	)
	post = models.ForeignKey(
		CulturalPost,
		on_delete=models.CASCADE,
		related_name="upvotes",
	)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=["user", "post"], name="unique_user_post_upvote"),
		]
		indexes = [
			models.Index(fields=["post", "created_at"], name="upvote_post_created_idx"),
		]

	def __str__(self):
		return f"{self.user.username} upvoted post #{self.post_id}"


class UserActivity(models.Model):
	"""
	Track user online/offline status and typing indicators.
	Used for real-time chat features like online status and typing indicators.
	"""
	user = models.OneToOneField(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="activity",
	)
	last_seen = models.DateTimeField(auto_now=True, db_index=True)
	is_online = models.BooleanField(default=False)
	typing_in_conversation = models.ForeignKey(
		Conversation,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="users_typing",
	)
	typing_started_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		ordering = ["-last_seen"]
		indexes = [
			models.Index(fields=["is_online", "last_seen"], name="useractivity_status_idx"),
		]

	def __str__(self):
		status = "online" if self.is_online else "offline"
		return f"{self.user.username} - {status}"

	@property
	def is_actually_online(self):
		"""Check if user should be considered online based on last_seen timestamp."""
		if not self.is_online:
			return False
		# After 5 minutes of inactivity, mark as offline
		cutoff_time = timezone.now() - timedelta(minutes=5)
		return self.last_seen > cutoff_time


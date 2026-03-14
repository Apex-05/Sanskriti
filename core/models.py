from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .quiz_utils import (
	QUIZ_CATEGORY_CHOICES,
	QUIZ_DIFFICULTY_CHOICES,
	build_generated_question_data,
	derive_post_tags,
	normalize_post_category,
)


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

	def __str__(self):
		return f"Profile of {self.user.username}"


class CulturalPost(models.Model):
	CATEGORY_CHOICES = [
		("festival", "Festival"),
		("food", "Food"),
		("ritual", "Ritual"),
		("craft", "Craft"),
		("music", "Music"),
		("dance", "Dance"),
		("folklore", "Folklore"),
		("architecture", "Architecture"),
		("other", "Other"),
	]

	author = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="cultural_posts",
	)
	title = models.CharField(max_length=150)
	category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
	description = models.TextField()
	image = models.ImageField(upload_to="uploads/cultural_posts/")
	latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
	longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]

	def __str__(self):
		return f"{self.title} ({self.author.username})"

	@property
	def quiz_category(self):
		return normalize_post_category(self.category)

	@property
	def quiz_tags(self):
		return derive_post_tags(self)

	def build_quiz_question_data(self):
		return build_generated_question_data(self)


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
	category = models.CharField(max_length=20, choices=QUIZ_CATEGORY_CHOICES)
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

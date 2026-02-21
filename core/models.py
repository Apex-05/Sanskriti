from django.conf import settings
from django.db import models


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

import json
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile

from .models import CulturalCategory, CulturalPost, QuizQuestion, QuizResult, UserProfile
from .services.culture import build_culture_comparison_context
from .services.karma import register_post_contribution


class TestCorePages(TestCase):
	def test_home_page_loads(self):
		response = self.client.get(reverse('home'))
		self.assertEqual(response.status_code, 200)

	def test_about_page_loads(self):
		response = self.client.get(reverse('about'))
		self.assertEqual(response.status_code, 200)


class TestCultureComparisonFormatting(TestCase):
	def test_text_mode_joins_keyword_lists_for_table_cells(self):
		raw_payload = {
			'Karnataka': {
				'ritual_practices': ['Mysuru Dasara', 'Ugadi new year puja'],
			},
			'Kerala': {
				'ritual_practices': ['Onam harvest', 'Vishu Kani'],
			},
		}

		with patch('core.services.culture._read_culture_payload', return_value=raw_payload):
			context = build_culture_comparison_context(left_name='Karnataka', right_name='Kerala')

		self.assertEqual(context['comparison_value_mode'], 'descriptive')
		row = next(item for item in context['comparison_rows'] if item['label'] == 'Ritual Practices')
		self.assertEqual(row['left_items'], ['Mysuru Dasara', 'Ugadi new year puja'])
		self.assertEqual(row['right_items'], ['Onam harvest', 'Vishu Kani'])
		self.assertEqual(row['left_value'], 'Mysuru Dasara, Ugadi new year puja')
		self.assertEqual(row['right_value'], 'Onam harvest, Vishu Kani')


class TestAuthFlow(TestCase):
	def test_register_creates_user_and_logs_in(self):
		response = self.client.post(
			reverse('register'),
			{
				'username': 'newuser',
				'email': 'newuser@example.com',
				'location': 'Bengaluru, Karnataka',
				'primary_region': 'south_india',
				'languages': 'Hindi - English - Kannada',
				'password1': 'StrongPass123!',
				'password2': 'StrongPass123!',
			},
			follow=True,
		)
		self.assertEqual(response.status_code, 200)
		self.assertTrue(User.objects.filter(username='newuser').exists())
		self.assertTrue(response.context['user'].is_authenticated)
		self.assertTrue(UserProfile.objects.filter(user__username='newuser').exists())

	def test_login_with_valid_credentials(self):
		User.objects.create_user(username='tester', password='StrongPass123!')
		response = self.client.post(
			reverse('login'),
			{'username': 'tester', 'password': 'StrongPass123!'},
			follow=True,
		)
		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.context['user'].is_authenticated)

	def test_edit_profile_updates_allowed_fields(self):
		user = User.objects.create_user(
			username='profileuser',
			email='profile@example.com',
			password='StrongPass123!',
		)
		UserProfile.objects.create(
			user=user,
			location='Bengaluru, Karnataka',
			primary_region='south_india',
			languages='Hindi - English',
		)

		self.client.login(username='profileuser', password='StrongPass123!')
		response = self.client.post(
			reverse('edit_profile'),
			{
				'location': 'Mysuru, Karnataka',
				'primary_region': 'south_india',
				'languages': 'Hindi - English - Kannada',
			},
			follow=True,
		)

		self.assertEqual(response.status_code, 200)
		profile = UserProfile.objects.get(user=user)
		self.assertEqual(profile.location, 'Mysuru, Karnataka')
		self.assertEqual(profile.languages, 'Hindi - English - Kannada')


class TestQuizSystem(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(username='quizuser', password='StrongPass123!')
		self.client.force_login(self.user)

		categories = ['festival', 'dance', 'heritage', 'food', 'language', 'ritual']
		answers = ['a', 'b', 'c', 'd']
		for index in range(60):
			category = categories[index % len(categories)]
			correct_answer = answers[index % len(answers)]
			QuizQuestion.objects.create(
				question_text=f'Question {index + 1} in {category}?',
				option_a=f'Option A {index + 1}',
				option_b=f'Option B {index + 1}',
				option_c=f'Option C {index + 1}',
				option_d=f'Option D {index + 1}',
				correct_answer=correct_answer,
				category=category,
				tags=[category],
				difficulty='medium',
				explanation=f'Explanation for question {index + 1}.',
				created_by=self.user,
				approved=True,
			)

	def _json_headers(self):
		return {
			'HTTP_ACCEPT': 'application/json',
			'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest',
		}

	def test_quiz_page_uses_practice_mode_context(self):
		response = self.client.get(reverse('quiz'))
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context['quiz_mode'], 'practice')
		self.assertEqual(response.context['mode_config']['question_count'], 10)

	def test_practice_quiz_json_returns_ten_questions(self):
		response = self.client.get(reverse('quiz_practice'), **self._json_headers())
		self.assertEqual(response.status_code, 200)
		payload = response.json()

		self.assertEqual(payload['mode'], 'practice')
		self.assertEqual(payload['duration_seconds'], 0)
		self.assertTrue(payload['instant_feedback'])
		self.assertTrue(payload['can_reset'])
		self.assertEqual(len(payload['questions']), 10)

	def test_timed_quiz_json_returns_ten_questions_and_ten_minute_timer(self):
		response = self.client.get(reverse('quiz_timed'), **self._json_headers())
		self.assertEqual(response.status_code, 200)
		payload = response.json()

		self.assertEqual(payload['mode'], 'timed')
		self.assertTrue(payload['has_timer'])
		self.assertEqual(payload['duration_seconds'], 600)
		self.assertFalse(payload['can_reset'])
		self.assertEqual(len(payload['questions']), 10)

	def test_daily_quiz_json_returns_two_questions(self):
		response = self.client.get(reverse('quiz_daily'), **self._json_headers())
		self.assertEqual(response.status_code, 200)
		payload = response.json()

		self.assertEqual(payload['mode'], 'daily')
		self.assertFalse(payload['has_timer'])
		self.assertFalse(payload['can_reset'])
		self.assertEqual(len(payload['questions']), 2)

	def test_timed_quiz_category_filter_limits_results(self):
		response = self.client.get(reverse('quiz_timed'), {'category': 'festival'}, **self._json_headers())
		self.assertEqual(response.status_code, 200)
		payload = response.json()

		self.assertEqual(len(payload['questions']), 10)
		self.assertTrue(all(question['category'] == 'festival' for question in payload['questions']))

	def test_daily_quiz_submission_is_only_allowed_once_per_day(self):
		payload = {
			'total_questions': 2,
			'correct_answers': 1,
			'incorrect_answers': 1,
		}

		first_response = self.client.post(
			reverse('quiz_daily'),
			data=json.dumps(payload),
			content_type='application/json',
		)
		self.assertEqual(first_response.status_code, 200)
		self.assertEqual(QuizResult.objects.count(), 1)

		second_response = self.client.post(
			reverse('quiz_daily'),
			data=json.dumps(payload),
			content_type='application/json',
		)
		self.assertEqual(second_response.status_code, 409)

		locked_response = self.client.get(reverse('quiz_daily'), **self._json_headers())
		locked_payload = locked_response.json()
		self.assertTrue(locked_payload['daily_locked'])
		self.assertEqual(len(locked_payload['questions']), 0)

	def test_leaderboard_payload_is_limited_to_top_ten(self):
		for index in range(12):
			leader_user = User.objects.create_user(username=f'leader_{index}', password='StrongPass123!')
			QuizResult.objects.create(
				user=leader_user,
				mode='practice' if index % 2 == 0 else 'timed',
				score=10,
				total_questions=10,
				correct_answers=10,
				incorrect_answers=0,
				percentage=100 - index,
			)

		response = self.client.get(reverse('quiz_practice'), **self._json_headers())
		payload = response.json()

		self.assertEqual(len(payload['leaderboard']), 10)
		self.assertIn('username', payload['leaderboard'][0])
		self.assertIn('mode', payload['leaderboard'][0])
		self.assertIn('played_on', payload['leaderboard'][0])


class TestContributionSystem(TestCase):
	def setUp(self):
		self.author = User.objects.create_user(username='author_user', password='StrongPass123!')
		self.viewer = User.objects.create_user(username='viewer_user', password='StrongPass123!')

		self.category, _ = CulturalCategory.objects.get_or_create(
			slug='festival',
			defaults={
				'name': 'Festivals',
				'description': 'Festival stories',
				'is_active': True,
				'display_order': 10,
			},
		)

		UserProfile.objects.create(
			user=self.author,
			location='Mysuru',
			primary_region='south_india',
			languages='English',
		)

	def _build_test_post(self, title, region_key, location_name='Mysuru', state_ut='Karnataka'):
		image_file = SimpleUploadedFile(
			name=f"{title.replace(' ', '_')}.jpg",
			content=b'fake-image-bytes',
			content_type='image/jpeg',
		)

		post = CulturalPost.objects.create(
			author=self.author,
			title=title,
			category='festival',
			description='Community cultural test story.',
			image=image_file,
			location_name=location_name,
			state_ut=state_ut,
			region_key=region_key,
		)
		post.categories.add(self.category)
		return post

	def test_karma_thresholds_award_without_duplicate_region_counting(self):
		for index in range(5):
			post = self._build_test_post(
				title=f'Story {index + 1}',
				region_key='state:karnataka|location:mysuru',
			)
			register_post_contribution(post)

		profile = UserProfile.objects.get(user=self.author)
		self.assertEqual(profile.posts_count, 5)
		self.assertEqual(profile.unique_regions_count, 1)
		self.assertEqual(profile.karma_points, 0)

		post_two = self._build_test_post(
			title='Story 6',
			region_key='state:kerala|location:kochi',
			location_name='Kochi',
			state_ut='Kerala',
		)
		register_post_contribution(post_two)

		post_three = self._build_test_post(
			title='Story 7',
			region_key='state:tamil nadu|location:madurai',
			location_name='Madurai',
			state_ut='Tamil Nadu',
		)
		register_post_contribution(post_three)

		post_four = self._build_test_post(
			title='Story 8',
			region_key='state:rajasthan|location:jaipur',
			location_name='Jaipur',
			state_ut='Rajasthan',
		)
		register_post_contribution(post_four)

		post_five = self._build_test_post(
			title='Story 9',
			region_key='state:ladakh|location:leh',
			location_name='Leh',
			state_ut='Ladakh',
		)
		register_post_contribution(post_five)

		profile.refresh_from_db()
		self.assertEqual(profile.posts_count, 9)
		self.assertEqual(profile.unique_regions_count, 5)
		self.assertEqual(profile.karma_points, 1)

	def test_upvote_endpoint_prevents_duplicates_and_updates_owner_karma(self):
		post = self._build_test_post(
			title='Upvote Story',
			region_key='state:karnataka|location:mysuru',
		)

		self.client.login(username='viewer_user', password='StrongPass123!')

		first_response = self.client.post(reverse('upvote_post', args=[post.id]))
		self.assertEqual(first_response.status_code, 200)
		self.assertFalse(first_response.json()['already_upvoted'])

		post.refresh_from_db()
		self.assertEqual(post.upvote_count, 1)

		author_profile = UserProfile.objects.get(user=self.author)
		self.assertEqual(author_profile.karma_points, 0)
		self.assertEqual(author_profile.upvotes_received, 1)

		second_response = self.client.post(reverse('upvote_post', args=[post.id]))
		self.assertEqual(second_response.status_code, 200)
		self.assertTrue(second_response.json()['already_upvoted'])

		post.refresh_from_db()
		self.assertEqual(post.upvote_count, 1)

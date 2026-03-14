import json

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User

from .models import QuizQuestion, QuizResult, UserProfile


class TestCorePages(TestCase):
	def test_home_page_loads(self):
		response = self.client.get(reverse('home'))
		self.assertEqual(response.status_code, 200)

	def test_about_page_loads(self):
		response = self.client.get(reverse('about'))
		self.assertEqual(response.status_code, 200)


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

	def test_learn_page_uses_practice_mode_context(self):
		response = self.client.get(reverse('learn'))
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context['quiz_mode'], 'practice')
		self.assertEqual(response.context['mode_config']['question_count'], 10)

	def test_practice_quiz_json_returns_ten_questions(self):
		response = self.client.get(reverse('practice_quiz'), **self._json_headers())
		self.assertEqual(response.status_code, 200)
		payload = response.json()

		self.assertEqual(payload['mode'], 'practice')
		self.assertEqual(payload['duration_seconds'], 0)
		self.assertTrue(payload['instant_feedback'])
		self.assertTrue(payload['can_reset'])
		self.assertEqual(len(payload['questions']), 10)

	def test_timed_quiz_json_returns_ten_questions_and_ten_minute_timer(self):
		response = self.client.get(reverse('timed_quiz'), **self._json_headers())
		self.assertEqual(response.status_code, 200)
		payload = response.json()

		self.assertEqual(payload['mode'], 'timed')
		self.assertTrue(payload['has_timer'])
		self.assertEqual(payload['duration_seconds'], 600)
		self.assertFalse(payload['can_reset'])
		self.assertEqual(len(payload['questions']), 10)

	def test_daily_quiz_json_returns_two_questions(self):
		response = self.client.get(reverse('daily_quiz'), **self._json_headers())
		self.assertEqual(response.status_code, 200)
		payload = response.json()

		self.assertEqual(payload['mode'], 'daily')
		self.assertFalse(payload['has_timer'])
		self.assertFalse(payload['can_reset'])
		self.assertEqual(len(payload['questions']), 2)

	def test_timed_quiz_category_filter_limits_results(self):
		response = self.client.get(reverse('timed_quiz'), {'category': 'festival'}, **self._json_headers())
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
			reverse('daily_quiz'),
			data=json.dumps(payload),
			content_type='application/json',
		)
		self.assertEqual(first_response.status_code, 200)
		self.assertEqual(QuizResult.objects.count(), 1)

		second_response = self.client.post(
			reverse('daily_quiz'),
			data=json.dumps(payload),
			content_type='application/json',
		)
		self.assertEqual(second_response.status_code, 409)

		locked_response = self.client.get(reverse('daily_quiz'), **self._json_headers())
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

		response = self.client.get(reverse('practice_quiz'), **self._json_headers())
		payload = response.json()

		self.assertEqual(len(payload['leaderboard']), 10)
		self.assertIn('username', payload['leaderboard'][0])
		self.assertIn('mode', payload['leaderboard'][0])
		self.assertIn('played_on', payload['leaderboard'][0])

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User


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
				'password1': 'StrongPass123!',
				'password2': 'StrongPass123!',
			},
			follow=True,
		)
		self.assertEqual(response.status_code, 200)
		self.assertTrue(User.objects.filter(username='newuser').exists())
		self.assertTrue(response.context['user'].is_authenticated)

	def test_login_with_valid_credentials(self):
		User.objects.create_user(username='tester', password='StrongPass123!')
		response = self.client.post(
			reverse('login'),
			{'username': 'tester', 'password': 'StrongPass123!'},
			follow=True,
		)
		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.context['user'].is_authenticated)

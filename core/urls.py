from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name="home"),
    path('about/', views.about, name="about"),
    path('developers/', views.developers, name='developers'),
    path('register/', views.register, name="register"),
    path('dashboard/', views.dashboard, name="dashboard"),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('explore/', views.explore_india, name='explore_india'),
    path('culture/', views.culture, name='culture'),
    path('heritage/', views.heritage, name='heritage'),
    path('discover/', views.discover, name='discover'),
    path('learn/', views.learn_page, name='learn'),
    path('learn/practice/', views.practice_quiz, name='practice_quiz'),
    path('learn/timed/', views.timed_quiz, name='timed_quiz'),
    path('learn/daily/', views.daily_quiz, name='daily_quiz'),
    path('upload/', views.upload, name='upload'),
    path('my-posts/', views.my_posts, name='my_posts'),
    path('login/', views.SanskritiLoginView.as_view(), name='login'),
    path('logout/', views.logout_user, name='logout'),
]
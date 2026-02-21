from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name="home"),
    path('about/', views.about, name="about"),
    path('register/', views.register, name="register"),
    path('dashboard/', views.dashboard, name="dashboard"),
    path('upload/', views.upload, name='upload'),
    path('my-posts/', views.my_posts, name='my_posts'),
    path('login/', views.SanskritiLoginView.as_view(), name='login'),
    path('logout/', views.logout_user, name='logout'),
]
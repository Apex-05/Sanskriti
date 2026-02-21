from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.shortcuts import redirect, render

from .forms import CulturalPostForm, RegisterForm, SanskritiAuthenticationForm


@method_decorator(never_cache, name="dispatch")
class SanskritiLoginView(LoginView):
    template_name = "core/login.html"
    redirect_authenticated_user = True
    authentication_form = SanskritiAuthenticationForm

    def get_success_url(self):
        return reverse_lazy("dashboard")

    def form_valid(self, form):
        if not self.request.POST.get("remember_me"):
            self.request.session.set_expiry(0)
        return super().form_valid(form)


def _require_auth_for_dashboard(request):
    if request.user.is_authenticated:
        return None

    messages.info(request, "Please login to continue.")
    return redirect("login")

def home(request):
    return render(request, "core/home.html")

def about(request):
    return render(request, "core/about.html")

def register(request):
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("dashboard")
    else:
        form = RegisterForm()

    return render(request, "core/register.html", {"form": form})

@never_cache
def dashboard(request):
    auth_redirect = _require_auth_for_dashboard(request)
    if auth_redirect:
        return auth_redirect

    return render(request, "core/dashboard.html")


@never_cache
def upload(request):
    auth_redirect = _require_auth_for_dashboard(request)
    if auth_redirect:
        return auth_redirect

    form = CulturalPostForm()
    if request.method == "POST":
        form = CulturalPostForm(request.POST, request.FILES)
        if form.is_valid():
            messages.info(request, "Upload preview captured. Saving to database is not enabled yet.")
            return redirect("upload")

    return render(request, "core/upload.html", {"form": form})


@require_POST
def logout_user(request):
    logout(request)
    messages.info(request, "Logged out successfully.", extra_tags="auto-dismiss center-screen")
    return redirect("home")
import re

from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django import forms

from .models import CulturalPost


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)
    error_messages = {
        "password_mismatch": "Passwords do not match. Please re-enter them.",
    }

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()

        if not 4 <= len(username) <= 20:
            raise forms.ValidationError("Username must be between 4 and 20 characters.")

        if " " in username:
            raise forms.ValidationError("Username cannot contain spaces.")

        if not re.fullmatch(r"^[A-Za-z0-9_]+$", username):
            raise forms.ValidationError("Username can only contain letters, numbers, and underscore (_).")

        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Username already taken. Try another.")

        return username

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists. Please login.")

        return email

    def clean_password1(self):
        password = self.cleaned_data.get("password1") or ""

        if len(password) < 8:
            raise forms.ValidationError("Password must be at least 8 characters long.")
        if not re.search(r"[A-Z]", password):
            raise forms.ValidationError("Password must include at least one uppercase letter.")
        if not re.search(r"[a-z]", password):
            raise forms.ValidationError("Password must include at least one lowercase letter.")
        if not re.search(r"\d", password):
            raise forms.ValidationError("Password must include at least one number.")
        if not re.search(r"[!@#$%^&*]", password):
            raise forms.ValidationError("Password must include at least one special character (!@#$%^&*).")

        return password

class SanskritiAuthenticationForm(AuthenticationForm):
    error_messages = {
        "invalid_login": "Invalid username or password.",
        "inactive": "This account is inactive.",
    }


class CulturalPostForm(forms.ModelForm):
    class Meta:
        model = CulturalPost
        fields = ["title", "category", "description", "image", "latitude", "longitude"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control form-control-lg",
                    "id": "postTitle",
                    "placeholder": "e.g., Bihu Harvest Celebrations",
                    "required": True,
                }
            ),
            "category": forms.Select(
                attrs={
                    "class": "form-select form-select-lg",
                    "id": "postCategory",
                    "required": True,
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "id": "postDescription",
                    "rows": 6,
                    "placeholder": "Describe the tradition, region, story, and context...",
                    "required": True,
                }
            ),
            "image": forms.ClearableFileInput(
                attrs={
                    "class": "d-none",
                    "id": "imageInput",
                    "accept": "image/*",
                    "required": True,
                }
            ),
            "latitude": forms.HiddenInput(attrs={"id": "latitude"}),
            "longitude": forms.HiddenInput(attrs={"id": "longitude"}),
        }

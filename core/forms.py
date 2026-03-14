import re

from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.db import DatabaseError
from django import forms

from .models import CulturalPost, UserProfile


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)
    location = forms.CharField(max_length=120, required=True)
    primary_region = forms.ChoiceField(choices=UserProfile.REGION_CHOICES, required=True)
    languages = forms.CharField(max_length=200, required=True)
    error_messages = {
        "password_mismatch": "Passwords do not match. Please re-enter them.",
    }

    class Meta:
        model = User
        fields = ['username', 'email', 'location', 'primary_region', 'languages', 'password1', 'password2']

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

    def clean_location(self):
        return (self.cleaned_data.get("location") or "").strip()

    def clean_languages(self):
        return (self.cleaned_data.get("languages") or "").strip()

    def save(self, commit=True):
        user = super().save(commit=commit)

        if commit:
            try:
                UserProfile.objects.update_or_create(
                    user=user,
                    defaults={
                        "location": self.cleaned_data["location"],
                        "primary_region": self.cleaned_data["primary_region"],
                        "languages": self.cleaned_data["languages"],
                    },
                )
            except DatabaseError:
                # If migrations are pending, skip profile persistence for now.
                pass

        return user

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



class ProfileForm(forms.ModelForm):

    class Meta:
        model = UserProfile
        fields = ['location', 'primary_region', 'languages']

        widgets = {
            'location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'City, State'
            }),
            'primary_region': forms.Select(attrs={
                'class': 'form-select'
            }),
            'languages': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Hindi, English, Kannada'
            }),
        }

    def clean_languages(self):
        languages = self.cleaned_data.get("languages", "").strip()

        if not languages:
            return languages

        # Accept common separators used by users (comma, hyphen, slash) without forcing reformatting.
        separators = [",", "-", "/"]
        has_separator = any(separator in languages for separator in separators)
        if has_separator:
            parts = [part.strip() for part in re.split(r"\s*(?:,|-|/)\s*", languages) if part.strip()]
            if not parts:
                raise forms.ValidationError("Please provide at least one language.")
            return languages

        # Single-language input is valid.
        return languages


# Alias kept for backward compatibility with views that import ProfileEditForm
ProfileEditForm = ProfileForm

import hashlib
import re
from io import BytesIO
from pathlib import Path

from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db import DatabaseError
from django import forms
from PIL import Image, ImageOps

from .constants import STATE_UT_CHOICES
from .models import CulturalCategory, CulturalPost, UserProfile
from .services.categories import get_active_categories


def _build_masked_password(raw_password):
    visible_prefix = (raw_password or "")[:3]
    hashed_remainder = hashlib.sha256((raw_password or "")[3:].encode("utf-8")).hexdigest()
    return f"{visible_prefix}{hashed_remainder}"


MAX_UPLOAD_IMAGE_WIDTH = 1600
MAX_UPLOAD_IMAGE_HEIGHT = 1600
JPEG_UPLOAD_QUALITY = 88


def _resize_uploaded_image(image_file, max_width=MAX_UPLOAD_IMAGE_WIDTH, max_height=MAX_UPLOAD_IMAGE_HEIGHT):
    if not image_file:
        return image_file

    try:
        if hasattr(image_file, "seek"):
            image_file.seek(0)

        with Image.open(image_file) as pil_image:
            normalized_image = ImageOps.exif_transpose(pil_image)
            normalized_image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

            output = BytesIO()
            has_alpha = normalized_image.mode in ("RGBA", "LA") or (
                normalized_image.mode == "P" and "transparency" in normalized_image.info
            )

            if has_alpha:
                if normalized_image.mode not in ("RGBA", "LA"):
                    normalized_image = normalized_image.convert("RGBA")
                target_format = "PNG"
                content_type = "image/png"
                target_ext = ".png"
                normalized_image.save(output, format=target_format, optimize=True)
            else:
                if normalized_image.mode != "RGB":
                    normalized_image = normalized_image.convert("RGB")
                target_format = "JPEG"
                content_type = "image/jpeg"
                target_ext = ".jpg"
                normalized_image.save(
                    output,
                    format=target_format,
                    optimize=True,
                    quality=JPEG_UPLOAD_QUALITY,
                    progressive=True,
                )

            output.seek(0)
            source_name = Path(getattr(image_file, "name", "upload") or "upload")
            generated_name = f"{source_name.stem or 'upload'}{target_ext}"

            return InMemoryUploadedFile(
                output,
                field_name=getattr(image_file, "field_name", None),
                name=generated_name,
                content_type=content_type,
                size=output.getbuffer().nbytes,
                charset=None,
            )
    except (OSError, ValueError):
        if hasattr(image_file, "seek"):
            image_file.seek(0)
        return image_file


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
                        "password": _build_masked_password(self.cleaned_data.get("password1") or ""),
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


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def clean(self, data, initial=None):
        single_file_clean = super().clean

        if isinstance(data, (list, tuple)):
            return [single_file_clean(item, initial) for item in data]

        cleaned_single = single_file_clean(data, initial)
        if cleaned_single:
            return [cleaned_single]
        return []


class CulturalPostForm(forms.ModelForm):
    categories = forms.ModelMultipleChoiceField(
        queryset=CulturalCategory.objects.none(),
        required=True,
        widget=forms.SelectMultiple(
            attrs={
                "class": "form-select form-select-lg",
                "id": "postCategory",
                "size": 6,
                "required": True,
            }
        ),
    )
    location_name = forms.CharField(
        required=False,
        max_length=200,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "id": "locationName",
                "placeholder": "Optional: City, village, landmark name",
            }
        ),
    )
    state_ut = forms.ChoiceField(
        required=False,
        choices=[("", "Select State / UT (optional)"), *STATE_UT_CHOICES],
        widget=forms.Select(
            attrs={
                "class": "form-select",
                "id": "stateUt",
            }
        ),
    )
    additional_images = MultipleFileField(
        required=False,
        widget=MultipleFileInput(
            attrs={
                "class": "d-none",
                "id": "additionalImagesInput",
                "accept": "image/*",
                "multiple": True,
            }
        ),
        help_text="Upload additional images (optional). You can select multiple files."
    )

    class Meta:
        model = CulturalPost
        fields = [
            "title",
            "categories",
            "description",
            "image",
            "location_name",
            "state_ut",
            "latitude",
            "longitude",
        ]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control form-control-lg",
                    "id": "postTitle",
                    "placeholder": "e.g., Bihu Harvest Celebrations",
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        active_categories = get_active_categories()
        self.fields["categories"].queryset = active_categories
        self.fields["categories"].help_text = "Select one or more cultural categories for this story."

        if self.instance and self.instance.pk:
            selected_category_ids = list(self.instance.categories.values_list("pk", flat=True))
            if not selected_category_ids and self.instance.category:
                primary_category = active_categories.filter(slug=self.instance.category).first()
                if primary_category:
                    selected_category_ids.append(primary_category.pk)

            self.initial["categories"] = selected_category_ids

    def clean(self):
        cleaned_data = super().clean()
        latitude = cleaned_data.get("latitude")
        longitude = cleaned_data.get("longitude")

        if (latitude is None) != (longitude is None):
            raise forms.ValidationError("Please provide both latitude and longitude or leave both empty.")

        return cleaned_data

    def clean_image(self):
        image_file = self.cleaned_data.get("image")
        if image_file and not getattr(image_file, "content_type", "").startswith("image/"):
            raise forms.ValidationError("Only image files are allowed for the primary upload.")

        return _resize_uploaded_image(image_file)
    
    def clean_additional_images(self):
        additional_images = self.cleaned_data.get("additional_images") or []

        if len(additional_images) > 10:
            raise forms.ValidationError("You can upload a maximum of 10 additional images.")

        resized_images = []
        for image_file in additional_images:
            if not getattr(image_file, "content_type", "").startswith("image/"):
                raise forms.ValidationError("Only image files are allowed for additional uploads.")

            resized_images.append(_resize_uploaded_image(image_file))

        return resized_images

    def save_categories(self, post):
        selected_categories = list(self.cleaned_data.get("categories") or [])
        post.categories.set(selected_categories)

    def save(self, commit=True):
        post = super().save(commit=False)
        selected_categories = list(self.cleaned_data.get("categories") or [])
        if selected_categories:
            post.category = selected_categories[0].slug
        post.location_name = (self.cleaned_data.get("location_name") or "").strip()
        post.state_ut = (self.cleaned_data.get("state_ut") or "").strip()

        if commit:
            post.save()
            self.save_categories(post)

        return post

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

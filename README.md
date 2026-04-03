# Sanskriti

Sanskriti is a Django-based cultural discovery and community platform focused on Indian heritage. It allows users to upload and explore cultural stories, discover region-wise contributions, learn through quizzes, and play an image-based culture quest game.

The project is designed as a full-stack web application using Django templates, SQLite/PostgreSQL-ready database configuration, static assets, and media uploads.

## Project Overview

Sanskriti provides the following core capabilities:

- User registration, login, and profile management
- Cultural post uploads with image support and categories
- State and region-based discovery views
- Upvotes and contribution tracking
- Quiz system (practice, timed, and daily challenge)
- Culture Quest game based on cultural images
- Chat and activity features
- Dashboard with user contribution metrics

## Tech Stack

- Python 3.10+
- Django 5.x
- SQLite (default local development)
- PostgreSQL/Supabase (optional via DATABASE_URL)
- HTML templates, CSS, JavaScript

## Repository Structure

Top-level files and folders:

- manage.py: Django management entry point
- requirements.txt: Python dependencies
- db.sqlite3: Local SQLite database (development)
- README.md: Project documentation
- core/: Main Django app (models, views, forms, templates, services)
- data/: Seed JSON files for culture and quiz content
- media/: Uploaded files (user images)
- static/: CSS, JavaScript, and static image assets
- sanskriti/: Django project settings and URL configuration

Important directories inside core:

- models.py: Data models for users, posts, quiz, quest, chat, and related entities
- views.py: Request handlers for all pages and APIs
- forms.py: Form definitions and validation
- urls.py: App-level URL routes
- quiz_utils.py: Quiz-related helpers
- services/: Modular business logic (culture quest, categories, karma, geocoding, and more)
- templates/core/: UI templates for all pages
- migrations/: Database schema migrations
- tests.py: Test cases

## Main Features

### Authentication and Profile

- Register and login workflows
- User profile editing
- Personal dashboard with contribution insights

### Cultural Content

- Upload cultural posts with metadata and media
- Browse and discover posts by region/state
- Spotlight and culture pages
- Upvote support

### Quiz and Learning

- Practice mode
- Timed mode
- Daily challenge mode
- Question sources from JSON and database entries

### Culture Quest

- Image-driven guessing game based on cultural posts
- Multiple game modes
- Scoring, progress, and leaderboard

### Community and Interaction

- Chat modules with user activity status
- Contribution and karma logic

## How to Run Locally

Follow these steps in order.

### 1. Clone the repository

```bash
git clone <your-repo-url>

```

### 2. Create and activate a virtual environment

Windows Git Bash:

```bash
python -m venv ../venv
source ../venv/Scripts/activate
```

Windows Command Prompt:

```bat
python -m venv ..\venv
..\venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### 5. Start the development server on port 8080

```bash
python manage.py runserver 8080
```

Open in browser:

http://127.0.0.1:8080/

## Environment Configuration

The project supports DATABASE_URL in environment variables for PostgreSQL/Supabase. If DATABASE_URL is not set, it defaults to local SQLite.

Optional local setup:

- Create a .env file in the sanskriti directory
- Add DATABASE_URL if using Supabase/PostgreSQL

## Useful Management Commands

```bash
python manage.py check
python manage.py createsuperuser
python manage.py showmigrations
```

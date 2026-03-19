import json
from pathlib import Path

# Build paths to data files
PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / 'data'
if not DATA_DIR.exists():
    DATA_DIR = PROJECT_DIR.parent / 'data'


def _load_json_file(filename):
    """Load JSON data file with graceful fallback."""
    filepath = DATA_DIR / filename
    if filepath.exists():
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return None


# Load data from JSON files
_states_data = _load_json_file('indian_states_uts.json')
_categories_data = _load_json_file('categories.json')

# Karma thresholds are configurable in one place for reuse across services and UI.
# 1 karma point per 5 different contributed locations.
KARMA_REGION_THRESHOLD = 5

# Indian states and UTs loaded from JSON
INDIAN_STATES_AND_UTS = _states_data or [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
    "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram",
    "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu",
    "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
    "Andaman and Nicobar Islands", "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu", "Delhi",
    "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
]

STATE_UT_CHOICES = [
    (state_name, state_name)
    for state_name in INDIAN_STATES_AND_UTS
]

# Cultural categories loaded from JSON
DEFAULT_CULTURAL_CATEGORIES = _categories_data or [
    {
        "slug": "festival",
        "name": "Festivals",
        "description": "Community celebrations, seasonal gatherings, and cultural fairs.",
        "display_order": 10,
    },
    {
        "slug": "food",
        "name": "Food",
        "description": "Regional cuisine, recipes, and culinary traditions.",
        "display_order": 20,
    },
    {
        "slug": "tradition",
        "name": "Traditions",
        "description": "Local customs and social practices passed through generations.",
        "display_order": 30,
    },
    {
        "slug": "clothing",
        "name": "Clothing",
        "description": "Traditional attire, textiles, and ornament styles.",
        "display_order": 40,
    },
    {
        "slug": "ritual",
        "name": "Rituals",
        "description": "Ceremonial and devotional practices tied to identity.",
        "display_order": 50,
    },
    {
        "slug": "language",
        "name": "Language",
        "description": "Dialect, oral narratives, scripts, and linguistic heritage.",
        "display_order": 60,
    },
    {
        "slug": "dance",
        "name": "Dance",
        "description": "Classical and folk performance traditions.",
        "display_order": 70,
    },
    {
        "slug": "music",
        "name": "Music",
        "description": "Regional music forms and instruments.",
        "display_order": 80,
    },
    {
        "slug": "folklore",
        "name": "Folklore",
        "description": "Stories, myths, oral memory, and local narratives.",
        "display_order": 90,
    },
    {
        "slug": "architecture",
        "name": "Architecture",
        "description": "Built heritage, monuments, and vernacular structures.",
        "display_order": 100,
    },
    {
        "slug": "heritage",
        "name": "Heritage",
        "description": "Cross-domain heritage topics and historical context.",
        "display_order": 110,
    },
    {
        "slug": "craft",
        "name": "Craft",
        "description": "Handmade traditions, artisan skills, and local making.",
        "display_order": 120,
    },
    {
        "slug": "other",
        "name": "Other",
        "description": "Cultural stories that do not fit existing groups.",
        "display_order": 130,
    },
]

DEFAULT_QUIZ_CATEGORY_SLUGS = [
    "festival",
    "food",
    "tradition",
    "clothing",
    "ritual",
    "language",
    "dance",
    "music",
    "folklore",
    "architecture",
    "heritage",
]

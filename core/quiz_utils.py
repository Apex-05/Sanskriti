import random
import re

from django.utils.text import Truncator

from .constants import DEFAULT_QUIZ_CATEGORY_SLUGS, INDIAN_STATES_AND_UTS


QUIZ_DIFFICULTY_CHOICES = [
	("easy", "Easy"),
	("medium", "Medium"),
	("hard", "Hard"),
]

POST_CATEGORY_TO_QUIZ_CATEGORY = {
	"festival": "festival",
	"food": "food",
	"tradition": "tradition",
	"clothing": "clothing",
	"ritual": "ritual",
	"language": "language",
	"craft": "heritage",
	"music": "music",
	"dance": "dance",
	"folklore": "folklore",
	"architecture": "architecture",
	"heritage": "heritage",
	"other": "heritage",
}

QUIZ_CATEGORY_LABELS = {
	"festival": "Festival",
	"food": "Food",
	"tradition": "Tradition",
	"clothing": "Clothing",
	"ritual": "Ritual",
	"language": "Language",
	"dance": "Dance",
	"music": "Music",
	"folklore": "Folklore",
	"architecture": "Architecture",
	"heritage": "Heritage",
}

QUIZ_DATA_CATEGORY_ORDER = tuple(DEFAULT_QUIZ_CATEGORY_SLUGS)
QUIZ_DATA_BLOCK_SIZE = 100

TAG_KEYWORDS = {
	"festival": ("festival", "celebration", "harvest", "fair"),
	"dance": ("dance", "performance", "classical", "folk dance"),
	"music": ("music", "song", "instrument", "raga"),
	"folklore": ("folklore", "myth", "legend", "oral tale"),
	"architecture": ("architecture", "monument", "temple", "fort"),
	"heritage": ("heritage", "monument", "architecture", "temple"),
	"food": ("food", "dish", "cuisine", "recipe"),
	"tradition": ("tradition", "custom", "community", "ceremony"),
	"clothing": ("clothing", "attire", "textile", "weaving"),
	"language": ("language", "dialect", "speech", "oral tradition"),
	"ritual": ("ritual", "ceremony", "prayer", "devotion"),
}

QUIZ_CATEGORY_ALIASES = {
	"festivals": "festival",
	"foods": "food",
	"traditions": "tradition",
	"rituals": "ritual",
	"languages": "language",
	"dances": "dance",
	"musics": "music",
	"architectures": "architecture",
}

QUIZ_CATEGORY_TAG_MAP = {
	"festival": ("festival", "heritage"),
	"food": ("food", "heritage", "ritual"),
	"tradition": ("tradition", "heritage", "ritual"),
	"clothing": ("clothing", "heritage", "textile"),
	"ritual": ("ritual", "heritage"),
	"language": ("language", "heritage"),
	"dance": ("dance", "heritage"),
	"music": ("music", "heritage"),
	"folklore": ("folklore", "heritage", "oral"),
	"architecture": ("architecture", "heritage", "monument"),
	"heritage": ("heritage",),
}

CATEGORY_INFERENCE_PRIORITY = QUIZ_DATA_CATEGORY_ORDER

CATEGORY_INFERENCE_RANK = {
	category: index
	for index, category in enumerate(CATEGORY_INFERENCE_PRIORITY)
}

CATEGORY_INFERENCE_KEYWORDS = {
	"festival": (
		"festival",
		"mela",
		"bihu",
		"onam",
		"pongal",
		"navratri",
		"diwali",
		"dussehra",
		"chaturthi",
		"new year",
		"celebration",
	),
	"food": (
		"food",
		"dish",
		"cuisine",
		"meal",
		"recipe",
		"biryani",
		"curry",
		"sweet",
		"snack",
		"dessert",
		"rice",
		"spice",
		"kitchen",
	),
	"tradition": (
		"tradition",
		"custom",
		"samskara",
		"wedding",
		"family",
		"kinship",
		"hospitality",
		"namaste",
		"mangalsutra",
		"gotra",
		"joint family",
	),
	"clothing": (
		"clothing",
		"garment",
		"attire",
		"dress",
		"saree",
		"silk",
		"textile",
		"weaving",
		"weave",
		"embroider",
		"shawl",
		"fabric",
		"turban",
		"dhoti",
		"chador",
		"chappal",
		"jewellery",
		"jewelry",
	),
	"ritual": (
		"ritual",
		"puja",
		"aarti",
		"havan",
		"yagna",
		"abhishek",
		"pradakshina",
		"vrata",
		"fast",
		"mantra",
		"offering",
		"consecration",
		"tilak",
		"deity",
		"temple",
	),
	"language": (
		"language",
		"script",
		"speaker",
		"eighth schedule",
		"linguistic",
		"grammar",
		"literature",
		"sanskrit",
		"tamil",
		"hindi",
		"urdu",
		"bengali",
	),
	"dance": (
		"dance",
		"bharatanatyam",
		"kathak",
		"odissi",
		"kuchipudi",
		"manipuri",
		"mohiniyattam",
		"garba",
		"bhangra",
		"chhau",
		"ghoomar",
		"lavani",
		"mudra",
		"abhinaya",
	),
	"music": (
		"music",
		"raga",
		"rag",
		"tala",
		"khayal",
		"dhrupad",
		"carnatic",
		"hindustani",
		"tabla",
		"sitar",
		"veena",
		"mridangam",
		"qawwali",
		"ghazal",
		"bhajan",
		"kirtan",
	),
	"folklore": (
		"folklore",
		"legend",
		"myth",
		"fable",
		"oral",
		"storytelling",
		"ballad",
		"puppet",
		"jataka",
		"panchatantra",
		"vetala",
		"paheli",
	),
	"architecture": (
		"architecture",
		"monument",
		"temple",
		"fort",
		"palace",
		"cave",
		"stupa",
		"stepwell",
		"gopuram",
		"minaret",
		"unesco",
		"world heritage",
		"archaeological",
		"dravidian",
		"nagara",
		"vesara",
	),
	"heritage": (
		"heritage",
		"cultural",
		"preservation",
		"intangible",
	),
}


def _normalize_token(value):
	return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _coerce_tag_values(raw_tags):
	if isinstance(raw_tags, str):
		return [token.strip() for token in raw_tags.split(",")]
	if isinstance(raw_tags, (list, tuple, set)):
		return list(raw_tags)
	return []


def normalize_quiz_category(value, default="heritage"):
	normalized = _normalize_token(value)
	if not normalized:
		return default

	normalized = QUIZ_CATEGORY_ALIASES.get(normalized, normalized)
	if normalized in QUIZ_CATEGORY_LABELS:
		return normalized

	return default


def get_category_lookup_values(category):
	canonical_category = normalize_quiz_category(category)
	legacy_keys = [
		legacy_slug
		for legacy_slug, canonical_slug in QUIZ_CATEGORY_ALIASES.items()
		if canonical_slug == canonical_category
	]
	return sorted({canonical_category, *legacy_keys})


def get_default_category_tags(category):
	canonical_category = normalize_quiz_category(category)
	return list(QUIZ_CATEGORY_TAG_MAP.get(canonical_category, (canonical_category, "heritage")))


def extract_quiz_category_from_tags(raw_tags, default=""):
	for raw_tag in _coerce_tag_values(raw_tags):
		normalized_tag = _normalize_token(raw_tag)
		if not normalized_tag:
			continue

		canonical_tag = QUIZ_CATEGORY_ALIASES.get(normalized_tag, normalized_tag)
		if canonical_tag in QUIZ_CATEGORY_LABELS:
			return canonical_tag

	return default


def infer_quiz_category_from_text(question_text="", explanation="", fallback="heritage"):
	haystack = f"{question_text or ''} {explanation or ''}".lower()
	if not haystack.strip():
		return fallback

	scores = {}
	for category, keywords in CATEGORY_INFERENCE_KEYWORDS.items():
		score = 0
		for keyword in keywords:
			if keyword in haystack:
				score += 1
		if score:
			scores[category] = score

	if not scores:
		return fallback

	best_category, _ = max(
		scores.items(),
		key=lambda item: (item[1], -CATEGORY_INFERENCE_RANK[item[0]]),
	)
	return best_category


def resolve_quiz_question_category(raw_category, raw_tags=None, question_text="", explanation=""):
	explicit_category = normalize_quiz_category(raw_category, default="")
	if explicit_category:
		return explicit_category

	tagged_category = extract_quiz_category_from_tags(raw_tags, default="")
	if tagged_category:
		return tagged_category

	return infer_quiz_category_from_text(question_text, explanation, fallback="heritage")


def normalize_quiz_tags(category, raw_tags):
	canonical_category = normalize_quiz_category(category)
	normalized_tags = set(get_default_category_tags(canonical_category))
	normalized_tags.add(canonical_category)

	raw_values = _coerce_tag_values(raw_tags)

	for raw_tag in raw_values:
		normalized_tag = _normalize_token(raw_tag)
		if not normalized_tag:
			continue
		normalized_tags.add(QUIZ_CATEGORY_ALIASES.get(normalized_tag, normalized_tag))

	return sorted(normalized_tags)


def normalize_post_category(post_category):
	normalized_post_category = _normalize_token(post_category)
	normalized_post_category = QUIZ_CATEGORY_ALIASES.get(normalized_post_category, normalized_post_category)
	mapped_category = POST_CATEGORY_TO_QUIZ_CATEGORY.get(normalized_post_category, normalized_post_category)
	return normalize_quiz_category(mapped_category, default="tradition")


def derive_post_tags(post):
	quiz_category = normalize_post_category(post.category)
	tags = set(get_default_category_tags(quiz_category))
	search_text = f"{post.title} {post.description}".lower()

	for tag, keywords in TAG_KEYWORDS.items():
		if any(keyword in search_text for keyword in keywords):
			tags.add(tag)

	return normalize_quiz_tags(quiz_category, tags)


def extract_state_reference(text):
	for state in INDIAN_STATES_AND_UTS:
		pattern = rf"\b{re.escape(state)}\b"
		if re.search(pattern, text, flags=re.IGNORECASE):
			return state

	return ""


def _clean_subject(title, state_name, category_label):
	subject = title.strip()

	if state_name:
		subject = re.sub(
			rf"\b(?:in|of|from)\s+{re.escape(state_name)}\b",
			"",
			subject,
			flags=re.IGNORECASE,
		)

	if category_label:
		subject = re.sub(rf"\b{re.escape(category_label)}\b", "", subject, flags=re.IGNORECASE)

	subject = re.sub(r"\s+", " ", subject).strip(" -:,")
	return subject or title.strip()


def _build_options(correct_option, option_pool):
	pool = [option for option in option_pool if option.lower() != correct_option.lower()]
	distractors = random.sample(pool, min(3, len(pool)))
	options = distractors + [correct_option]

	while len(options) < 4:
		fallback = f"Option {len(options) + 1}"
		if fallback not in options:
			options.append(fallback)

	random.shuffle(options)
	letters = ("a", "b", "c", "d")
	letter_map = {letter: value for letter, value in zip(letters, options)}
	correct_answer = next(letter for letter, value in letter_map.items() if value == correct_option)

	return {
		"option_a": letter_map["a"],
		"option_b": letter_map["b"],
		"option_c": letter_map["c"],
		"option_d": letter_map["d"],
		"correct_answer": correct_answer,
	}


def build_generated_question_data(post):
	quiz_category = normalize_post_category(post.category)
	category_label = quiz_category.replace("_", " ").title()
	state_reference = extract_state_reference(f"{post.title} {post.description}")
	subject = _clean_subject(post.title, state_reference, category_label)
	tags = derive_post_tags(post)

	if state_reference:
		question_text = f"Which state is most closely associated with {subject}?"
		option_data = _build_options(state_reference, INDIAN_STATES_AND_UTS)
		explanation = (
			f"This question was generated from the community post '{post.title}'. "
			f"{Truncator(post.description).chars(160)}"
		)
	else:
		question_text = f"Which cultural theme best matches the community upload '{post.title}'?"
		option_data = _build_options(category_label, list(QUIZ_CATEGORY_LABELS.values()))
		explanation = (
			f"The post is mapped to {category_label.lower()} based on its uploaded category and cultural context. "
			f"{Truncator(post.description).chars(140)}"
		)

	return {
		"question_text": question_text,
		**option_data,
		"category": quiz_category,
		"tags": tags,
		"difficulty": "medium",
		"explanation": explanation,
	}
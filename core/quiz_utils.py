import random
import re

from django.utils.text import Truncator


QUIZ_CATEGORY_CHOICES = [
	("festival", "Festival"),
	("dance", "Dance"),
	("heritage", "Heritage"),
	("food", "Food"),
	("language", "Language"),
	("ritual", "Ritual"),
]

QUIZ_DIFFICULTY_CHOICES = [
	("easy", "Easy"),
	("medium", "Medium"),
	("hard", "Hard"),
]

QUIZ_CATEGORY_LABELS = dict(QUIZ_CATEGORY_CHOICES)

POST_CATEGORY_TO_QUIZ_CATEGORY = {
	"festival": "festival",
	"food": "food",
	"ritual": "ritual",
	"craft": "heritage",
	"music": "dance",
	"dance": "dance",
	"folklore": "language",
	"architecture": "heritage",
	"other": "heritage",
}

QUIZ_CATEGORY_TO_POST_CATEGORIES = {
	"festival": ["festival"],
	"dance": ["dance", "music"],
	"heritage": ["architecture", "craft", "other"],
	"food": ["food"],
	"language": ["folklore"],
	"ritual": ["ritual"],
}

TAG_KEYWORDS = {
	"festival": ("festival", "celebration", "harvest", "fair"),
	"dance": ("dance", "music", "performance", "folk"),
	"heritage": ("heritage", "monument", "architecture", "temple"),
	"food": ("food", "dish", "cuisine", "recipe"),
	"language": ("language", "dialect", "speech", "oral tradition"),
	"ritual": ("ritual", "ceremony", "prayer", "devotion"),
}

STATE_OPTIONS = [
	"Andhra Pradesh",
	"Arunachal Pradesh",
	"Assam",
	"Bihar",
	"Chhattisgarh",
	"Goa",
	"Gujarat",
	"Haryana",
	"Himachal Pradesh",
	"Jharkhand",
	"Karnataka",
	"Kerala",
	"Madhya Pradesh",
	"Maharashtra",
	"Manipur",
	"Meghalaya",
	"Mizoram",
	"Nagaland",
	"Odisha",
	"Punjab",
	"Rajasthan",
	"Sikkim",
	"Tamil Nadu",
	"Telangana",
	"Tripura",
	"Uttar Pradesh",
	"Uttarakhand",
	"West Bengal",
]


def normalize_post_category(post_category):
	return POST_CATEGORY_TO_QUIZ_CATEGORY.get(post_category, "heritage")


def derive_post_tags(post):
	tags = {normalize_post_category(post.category)}
	search_text = f"{post.title} {post.description}".lower()

	for tag, keywords in TAG_KEYWORDS.items():
		if any(keyword in search_text for keyword in keywords):
			tags.add(tag)

	return sorted(tags)


def extract_state_reference(text):
	for state in STATE_OPTIONS:
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
	category_label = QUIZ_CATEGORY_LABELS[quiz_category]
	state_reference = extract_state_reference(f"{post.title} {post.description}")
	subject = _clean_subject(post.title, state_reference, category_label)
	tags = derive_post_tags(post)

	if state_reference:
		question_text = f"Which state is most closely associated with {subject}?"
		option_data = _build_options(state_reference, STATE_OPTIONS)
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
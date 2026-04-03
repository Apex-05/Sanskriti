"""
Culture Quest game logic and utilities.
GeoGuessr-style game where players guess regions/states from cultural images.
"""
import random
from django.db.models import Q, Count
from django.utils import timezone
from core.models import CulturalPost, CultureQuestSession, CultureQuestAnswer
from core.constants import INDIAN_STATES_AND_UTS


def get_random_post_for_quest(session=None, exclude_post_ids=None):
    """
    Get a random cultural post with valid state/location data for the game.
    
    Args:
        session: Optional CultureQuestSession to track used posts
        exclude_post_ids: List of post IDs to exclude
    
    Returns:
        CulturalPost or None
    """
    queryset = (
        CulturalPost.objects
        .exclude(state_ut="")
        .exclude(state_ut__isnull=True)
        .filter(image__isnull=False)
        .select_related("author")
    )
    
    # Exclude posts already used in this session
    if exclude_post_ids:
        queryset = queryset.exclude(id__in=exclude_post_ids)
    
    # Prefer posts with higher engagement for better quality
    queryset = queryset.filter(upvote_count__gte=0)
    
    # Get count and pick random
    count = queryset.count()
    if count == 0:
        return None
    
    random_index = random.randint(0, count - 1)
    return queryset[random_index]


def create_game_session(user, mode="quick", total_questions=10):
    """
    Create a new Culture Quest game session.
    
    Args:
        user: User instance
        mode: Game mode (quick, marathon, daily)
        total_questions: Number of questions in the session
    
    Returns:
        CultureQuestSession instance
    """
    session = CultureQuestSession.objects.create(
        user=user,
        mode=mode,
        total_questions=total_questions,
        correct_answers=0,
        score=0,
        is_complete=False,
    )
    return session


def get_next_question(session):
    """
    Get the next question for a game session.
    
    Args:
        session: CultureQuestSession instance
    
    Returns:
        dict with question data or None if session is complete
    """
    if session.is_complete:
        return None
    
    # Check how many questions have been answered
    answered_count = session.answers.count()
    if answered_count >= session.total_questions:
        return None
    
    # Get posts already used in this session
    used_post_ids = list(session.answers.values_list("post_id", flat=True))
    
    # Get random post
    post = get_random_post_for_quest(session=session, exclude_post_ids=used_post_ids)
    if not post:
        return None
    
    # Build question data
    question_data = {
        "question_number": answered_count + 1,
        "total_questions": session.total_questions,
        "post_id": post.id,
        "image_url": post.image.url if post.image else None,
        "title": post.title,
        "description": post.description,
        "category": post.get_category_display_name(),
        "state_options": get_state_options_for_question(post.state_ut),
    }
    
    return question_data


def get_state_options_for_question(correct_state, num_options=4):
    """
    Get multiple-choice state options for a question.
    
    Args:
        correct_state: The correct state name
        num_options: Total number of options to return (including correct)
    
    Returns:
        List of state names (shuffled, includes correct answer)
    """
    # Normalize correct state
    from core.services.geocoding import normalize_state_name
    correct_state = normalize_state_name(correct_state)
    
    # Get all states except the correct one
    other_states = [s for s in INDIAN_STATES_AND_UTS if s != correct_state]
    
    # Randomly select wrong answers
    num_wrong = min(num_options - 1, len(other_states))
    wrong_states = random.sample(other_states, num_wrong)
    
    # Combine and shuffle
    all_options = [correct_state] + wrong_states
    random.shuffle(all_options)
    
    return all_options


def submit_answer(session, post_id, guessed_state, time_taken_seconds=0):
    """
    Submit an answer for a Culture Quest question.
    
    Args:
        session: CultureQuestSession instance
        post_id: ID of the post being guessed
        guessed_state: User's guessed state name
        time_taken_seconds: Time taken to answer (optional)
    
    Returns:
        dict with result data
    """
    try:
        post = CulturalPost.objects.get(id=post_id)
    except CulturalPost.DoesNotExist:
        return {
            "success": False,
            "error": "Post not found",
        }
    
    from core.services.geocoding import normalize_state_name
    correct_state = normalize_state_name(post.state_ut)
    guessed_state_normalized = normalize_state_name(guessed_state)
    
    is_correct = guessed_state_normalized == correct_state
    
    # Calculate points (base 100, bonus for speed)
    points_earned = 0
    if is_correct:
        base_points = 100
        # Bonus points for answering quickly (max 50 bonus)
        if time_taken_seconds > 0 and time_taken_seconds <= 30:
            speed_bonus = int((30 - time_taken_seconds) * 1.67)  # 50 points at 0s, 0 at 30s
            points_earned = base_points + max(0, min(50, speed_bonus))
        else:
            points_earned = base_points
    
    # Create answer record
    answer = CultureQuestAnswer.objects.create(
        session=session,
        post=post,
        guessed_state=guessed_state,
        correct_state=correct_state,
        is_correct=is_correct,
        points_earned=points_earned,
        time_taken_seconds=time_taken_seconds,
    )
    
    # Update session stats
    if is_correct:
        session.correct_answers += 1
    session.score += points_earned
    
    # Check if session is complete
    answered_count = session.answers.count()
    if answered_count >= session.total_questions:
        session.is_complete = True
        session.completed_at = timezone.now()
    
    session.save()
    
    return {
        "success": True,
        "is_correct": is_correct,
        "correct_state": correct_state,
        "guessed_state": guessed_state,
        "points_earned": points_earned,
        "total_score": session.score,
        "correct_count": session.correct_answers,
        "answered_count": answered_count,
        "is_session_complete": session.is_complete,
        "post_location": post.location_name or correct_state,
        "post_title": post.title,
        "post_image_url": post.image.url if post.image else None,
    }


def get_leaderboard(mode="quick", limit=10):
    """
    Get top players for Culture Quest leaderboard.
    
    Args:
        mode: Game mode to filter by (or "all" for all modes)
        limit: Number of top players to return
    
    Returns:
        List of leaderboard entries
    """
    queryset = CultureQuestSession.objects.filter(is_complete=True)
    
    if mode != "all":
        queryset = queryset.filter(mode=mode)
    
    # Get top sessions by score
    top_sessions = (
        queryset
        .select_related("user")
        .order_by("-score", "-correct_answers", "completed_at")[:limit]
    )
    
    leaderboard = []
    for rank, session in enumerate(top_sessions, start=1):
        leaderboard.append({
            "rank": rank,
            "username": session.user.username,
            "score": session.score,
            "correct_answers": session.correct_answers,
            "total_questions": session.total_questions,
            "accuracy": session.accuracy_percentage,
            "mode": session.get_mode_display(),
            "completed_at": session.completed_at,
        })
    
    return leaderboard


def get_user_stats(user):
    """
    Get Culture Quest statistics for a user.
    
    Args:
        user: User instance
    
    Returns:
        dict with user stats
    """
    sessions = CultureQuestSession.objects.filter(user=user, is_complete=True)
    
    total_games = sessions.count()
    if total_games == 0:
        return {
            "total_games": 0,
            "total_score": 0,
            "average_score": 0,
            "best_score": 0,
            "total_correct": 0,
            "total_questions": 0,
            "overall_accuracy": 0,
        }
    
    total_score = sum(s.score for s in sessions)
    total_correct = sum(s.correct_answers for s in sessions)
    total_questions = sum(s.total_questions for s in sessions)
    best_score = max(s.score for s in sessions)
    
    return {
        "total_games": total_games,
        "total_score": total_score,
        "average_score": round(total_score / total_games),
        "best_score": best_score,
        "total_correct": total_correct,
        "total_questions": total_questions,
        "overall_accuracy": round((total_correct / total_questions * 100) if total_questions > 0 else 0),
    }

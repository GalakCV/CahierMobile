"""Indicadores do painel inicial."""
from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Sum
from django.utils import timezone

from content.models import Chapter, GrammarTopic

from .models import Attempt, Mastery, ReviewItem, UserSetting


def study_days() -> list:
    dates = set()
    for dt in Attempt.objects.values_list("created_at", flat=True):
        dates.add(timezone.localtime(dt).date())
    return sorted(dates)


def streak(today=None) -> int:
    """Dias consecutivos com estudo terminando hoje (ou ontem, se ainda não estudou hoje)."""
    days = set(study_days())
    if not days:
        return 0
    today = today or timezone.localdate()
    cursor = today if today in days else today - timedelta(days=1)
    count = 0
    while cursor in days:
        count += 1
        cursor -= timedelta(days=1)
    return count


def accuracy() -> float | None:
    graded = Attempt.objects.exclude(result=Attempt.Result.PENDING)
    total = graded.count()
    if not total:
        return None
    return round(100 * sum(graded.values_list("score", flat=True)) / total, 1)


def total_minutes() -> int:
    seconds = Attempt.objects.aggregate(s=Sum("duration_seconds"))["s"] or 0
    return round(seconds / 60)


def minutes_today() -> int:
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    seconds = Attempt.objects.filter(created_at__gte=start).aggregate(s=Sum("duration_seconds"))["s"] or 0
    return round(seconds / 60)


def competency_ranking(min_attempts: int = 3):
    rows = [m for m in Mastery.objects.filter(scope=Mastery.Scope.COMPETENCY)
            if m.details.get("attempts", 0) >= min_attempts]
    rows.sort(key=lambda m: m.score, reverse=True)
    strong = rows[:3]
    weak = sorted(rows, key=lambda m: m.details.get("accuracy", 0))[:3]
    weak = [m for m in weak if m not in strong or len(rows) <= 3]
    return strong, weak


def recurrent_errors(limit: int = 5):
    items = (ReviewItem.objects.filter(error_count__gt=0, exercise__is_active=True)
             .select_related("exercise", "exercise__chapter").order_by("-error_count", "-last_error_at")[:limit])
    topics = (GrammarTopic.objects.filter(exercises__review_item__error_count__gt=0)
              .annotate(errors=Sum("exercises__review_item__error_count"))
              .order_by("-errors")[:3])
    return list(items), list(topics)


def current_chapter():
    setting = UserSetting.get()
    if setting.current_chapter and setting.current_chapter.is_active:
        return setting.current_chapter
    last = Attempt.objects.select_related("exercise__chapter").first()
    if last:
        return last.exercise.chapter
    return Chapter.objects.filter(is_active=True, is_planned=False).order_by("number").first()


def overview() -> dict:
    overall = Mastery.objects.filter(scope=Mastery.Scope.OVERALL).first()
    chapters = Mastery.objects.filter(scope=Mastery.Scope.CHAPTER)
    chapter_scores = [m.score for m in chapters]
    active_chapters = Chapter.objects.filter(is_active=True, is_planned=False).count()
    general_progress = round(sum(chapter_scores) / active_chapters, 1) if active_chapters else 0.0
    strong, weak = competency_ranking()
    errors, error_topics = recurrent_errors()
    agg = Attempt.objects.aggregate(n=Count("id"), d=Count("exercise", distinct=True))
    return {
        "overall": overall,
        "general_progress": general_progress,
        "attempt_count": agg["n"],
        "distinct_exercises": agg["d"],
        "accuracy": accuracy(),
        "streak": streak(),
        "total_minutes": total_minutes(),
        "minutes_today": minutes_today(),
        "due_reviews": ReviewItem.objects.filter(due_at__lte=timezone.now(), exercise__is_active=True).count(),
        "strong": strong,
        "weak": weak,
        "errors": errors,
        "error_topics": error_topics,
        "current_chapter": current_chapter(),
    }

from django.contrib import admin

from .models import Attempt, Mastery, ReviewItem, SessionItem, StudySession, UserSetting, WrittenAnswer


class ReadOnlyAdmin(admin.ModelAdmin):
    """Histórico de estudo: consultável, mas não editável pelo painel."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Attempt)
class AttemptAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "exercise", "exercise_version", "result", "score", "mode", "duration_seconds")
    list_filter = ("result", "mode", "exercise__chapter")
    search_fields = ("exercise__code", "answer_display")
    date_hierarchy = "created_at"


class SessionItemInline(admin.TabularInline):
    model = SessionItem
    extra = 0
    fields = ("position", "exercise", "answered_at", "attempt")
    readonly_fields = fields
    can_delete = False


@admin.register(StudySession)
class StudySessionAdmin(ReadOnlyAdmin):
    list_display = ("__str__", "kind", "mode", "status", "started_at", "result_score")
    list_filter = ("kind", "mode", "status")
    inlines = [SessionItemInline]


@admin.register(ReviewItem)
class ReviewItemAdmin(ReadOnlyAdmin):
    list_display = ("exercise", "stage", "interval_days", "due_at", "error_count", "correct_streak", "recovery")
    list_filter = ("recovery", "stage", "flagged")
    search_fields = ("exercise__code",)


@admin.register(Mastery)
class MasteryAdmin(ReadOnlyAdmin):
    list_display = ("label", "scope", "score", "updated_at")
    list_filter = ("scope",)


@admin.register(WrittenAnswer)
class WrittenAnswerAdmin(admin.ModelAdmin):
    list_display = ("attempt", "assessed_score", "assessed_by", "marked_for_review")
    readonly_fields = ("attempt", "text", "criteria_checked", "assessed_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UserSetting)
class UserSettingAdmin(admin.ModelAdmin):
    list_display = ("__str__", "default_session_size", "daily_goal_minutes", "font_size", "theme")

    def has_delete_permission(self, request, obj=None):
        return False

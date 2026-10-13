"""
Painel administrativo de conteúdo (Django admin).

- Conteúdos não podem ser apagados pelo painel: use as ações "Ativar"/"Desativar".
- Ao salvar uma questão (com alternativas e respostas), uma nova versão é
  registrada automaticamente se algo avaliável mudou.
- O histórico de alterações de cada registro fica no botão "Histórico".
"""
from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html

from .models import (AcceptedAnswer, Chapter, Choice, Competency, ContentIssue, Course, Exercise,
                     ExerciseRelation, ExerciseVersion, GrammarTopic, LearningObjective, Passage,
                     Source, VocabularyItem, VocabularyTopic)

admin.site.site_header = "Cahier — painel de conteúdo"
admin.site.site_title = "Cahier (admin)"
admin.site.index_title = "Conteúdo pedagógico"
admin.site.site_url = "/"


@admin.action(description="Ativar selecionados")
def activate(modeladmin, request, queryset):
    n = queryset.update(is_active=True)
    messages.success(request, f"{n} registro(s) ativado(s).")


@admin.action(description="Desativar selecionados (o histórico é preservado)")
def deactivate(modeladmin, request, queryset):
    n = queryset.update(is_active=False)
    messages.success(request, f"{n} registro(s) desativado(s). Nada foi apagado.")


class NoDeleteMixin:
    """Preserva o histórico: exclusão desabilitada, use desativação."""

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "license_name", "url_link")
    search_fields = ("title", "author", "license_name", "notes")

    @admin.display(description="URL")
    def url_link(self, obj):
        return format_html('<a href="{}" rel="noreferrer noopener">{}</a>', obj.url, obj.url) if obj.url else "—"

    def has_delete_permission(self, request, obj=None):
        if obj and (obj.exercises.exists() or obj.passages.exists()):
            return False
        return super().has_delete_permission(request, obj)


@admin.register(Course)
class CourseAdmin(NoDeleteMixin, admin.ModelAdmin):
    list_display = ("title", "code")


@admin.register(Competency)
class CompetencyAdmin(NoDeleteMixin, admin.ModelAdmin):
    list_display = ("name", "code", "position")
    list_editable = ("position",)


class ObjectiveInline(admin.TabularInline):
    model = LearningObjective
    extra = 0
    fields = ("code", "description", "position", "is_active")
    show_change_link = True

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Chapter)
class ChapterAdmin(NoDeleteMixin, admin.ModelAdmin):
    list_display = ("number", "title", "theme", "cefr_level", "is_active", "is_planned", "exercise_count")
    list_display_links = ("number", "title")
    list_filter = ("is_active", "is_planned", "cefr_level")
    search_fields = ("title", "theme", "description")
    inlines = [ObjectiveInline]
    actions = [activate, deactivate]

    @admin.display(description="questões ativas")
    def exercise_count(self, obj):
        return obj.exercises.filter(is_active=True).count()


@admin.register(LearningObjective)
class LearningObjectiveAdmin(NoDeleteMixin, admin.ModelAdmin):
    list_display = ("description", "chapter", "is_active")
    list_filter = ("chapter", "is_active")
    search_fields = ("description", "code")
    filter_horizontal = ("competencies",)
    actions = [activate, deactivate]


@admin.register(GrammarTopic)
class GrammarTopicAdmin(NoDeleteMixin, admin.ModelAdmin):
    list_display = ("title", "chapter", "position", "is_active")
    list_filter = ("chapter", "is_active")
    search_fields = ("title", "summary", "code")
    actions = [activate, deactivate]


class VocabularyItemInline(admin.TabularInline):
    model = VocabularyItem
    extra = 1
    fields = ("french", "portuguese", "gender", "example", "position")


@admin.register(VocabularyTopic)
class VocabularyTopicAdmin(NoDeleteMixin, admin.ModelAdmin):
    list_display = ("title", "chapter", "item_count", "is_active")
    list_filter = ("chapter", "is_active")
    search_fields = ("title", "items__french", "items__portuguese")
    inlines = [VocabularyItemInline]
    actions = [activate, deactivate]

    @admin.display(description="palavras")
    def item_count(self, obj):
        return obj.items.count()


@admin.register(Passage)
class PassageAdmin(NoDeleteMixin, admin.ModelAdmin):
    list_display = ("title", "chapter", "text_type", "difficulty", "words", "origin", "review_status", "is_active")
    list_filter = ("chapter", "text_type", "difficulty", "origin", "review_status", "is_active")
    search_fields = ("title", "body", "code")
    filter_horizontal = ("grammar_topics", "vocabulary_topics")
    actions = [activate, deactivate]

    @admin.display(description="palavras")
    def words(self, obj):
        return obj.word_count


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 0
    fields = ("position", "text", "is_correct", "correct_position", "match_text", "feedback")


class AcceptedAnswerInline(admin.TabularInline):
    model = AcceptedAnswer
    extra = 0
    fields = ("blank_index", "text", "is_primary")


class VersionInline(admin.TabularInline):
    model = ExerciseVersion
    extra = 0
    fields = ("number", "created_at", "note", "content_hash")
    readonly_fields = fields
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


class RelationInline(admin.TabularInline):
    model = ExerciseRelation
    fk_name = "from_exercise"
    extra = 0
    autocomplete_fields = ("to_exercise",)


@admin.register(Exercise)
class ExerciseAdmin(NoDeleteMixin, admin.ModelAdmin):
    list_display = ("code", "chapter", "exercise_type", "difficulty", "competency", "is_assessment",
                    "origin", "review_status", "is_active", "version", "open_issues")
    list_filter = ("chapter", "exercise_type", "interaction", "difficulty", "competency", "is_assessment",
                   "origin", "review_status", "is_active", "comparison_mode")
    search_fields = ("code", "prompt", "instruction", "explanation")
    autocomplete_fields = ("passage",)
    filter_horizontal = ("objectives", "grammar_topics", "vocabulary_topics")
    readonly_fields = ("version", "preview_link")
    inlines = [ChoiceInline, AcceptedAnswerInline, RelationInline, VersionInline]
    actions = [activate, deactivate, "mark_reviewed"]
    save_on_top = True
    fieldsets = (
        ("Identificação", {"fields": ("code", "chapter", "passage", "exercise_type", "interaction",
                                      "is_assessment", "is_active", "position", "version", "preview_link")}),
        ("Conteúdo", {"fields": ("instruction", "context", "prompt", "translation_pt")}),
        ("Correção", {"fields": ("comparison_mode", "accent_insensitive", "explanation", "evidence",
                                 "model_answer", "criteria")}),
        ("Classificação", {"fields": ("difficulty", "cefr_level", "estimated_seconds", "competency",
                                      "objectives", "grammar_topics", "vocabulary_topics", "reading_skill")}),
        ("Fonte e revisão", {"fields": ("origin", "source", "adaptation_notes", "review_status")}),
    )

    @admin.display(description="pré-visualizar")
    def preview_link(self, obj):
        if not obj.pk:
            return "—"
        return format_html('<a href="{}" target="_blank">Abrir pré-visualização</a>',
                           reverse("content:exercise_preview", args=[obj.code]))

    @admin.display(description="problemas abertos")
    def open_issues(self, obj):
        n = obj.issues.filter(status=ContentIssue.Status.OPEN).count()
        return n or ""

    @admin.action(description="Marcar revisão pedagógica como concluída")
    def mark_reviewed(self, request, queryset):
        n = queryset.update(review_status="reviewed")
        messages.success(request, f"{n} questão(ões) marcada(s) como revisada(s).")

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        version = form.instance.snapshot_version("edição no painel administrativo")
        messages.info(request, f"Versão atual da questão: v{version.number}.")


@admin.register(ExerciseVersion)
class ExerciseVersionAdmin(admin.ModelAdmin):
    list_display = ("exercise", "number", "created_at", "note")
    list_filter = ("exercise__chapter",)
    search_fields = ("exercise__code",)
    readonly_fields = ("exercise", "number", "snapshot", "content_hash", "note", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ExerciseRelation)
class ExerciseRelationAdmin(admin.ModelAdmin):
    list_display = ("from_exercise", "kind", "to_exercise")
    list_filter = ("kind",)
    autocomplete_fields = ("from_exercise", "to_exercise")


@admin.register(ContentIssue)
class ContentIssueAdmin(admin.ModelAdmin):
    list_display = ("exercise", "kind", "status", "created_at", "short_comment")
    list_filter = ("status", "kind")
    search_fields = ("exercise__code", "comment")
    list_editable = ("status",)
    readonly_fields = ("exercise", "exercise_version", "kind", "comment", "user_answer", "created_at")

    @admin.display(description="comentário")
    def short_comment(self, obj):
        return (obj.comment[:80] + "…") if len(obj.comment) > 80 else obj.comment

    def has_delete_permission(self, request, obj=None):
        return False

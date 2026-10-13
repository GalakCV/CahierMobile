"""
Modelos de estudo: sessões, tentativas (imutáveis), produção escrita,
domínio calculado, fila de revisão espaçada e preferências.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from content.models import Chapter, Exercise


class StudySession(models.Model):
    class Mode(models.TextChoices):
        PRACTICE = "practice", "Prática (correção imediata)"
        ASSESSMENT = "assessment", "Avaliação (resultado no final)"

    class Kind(models.TextChoices):
        CUSTOM = "custom", "Sessão personalizada"
        CHAPTER_REVIEW = "chapter_review", "Revisão do capítulo"
        CHAPTER_ASSESSMENT = "chapter_assessment", "Avaliação do capítulo"
        SPACED_REVIEW = "spaced_review", "Revisões pendentes"
        PASSAGE = "passage", "Interpretação de texto"
        RETRY = "retry", "Refazer questões erradas"

    class Status(models.TextChoices):
        ACTIVE = "active", "Em andamento"
        PAUSED = "paused", "Interrompida"
        FINISHED = "finished", "Concluída"

    mode = models.CharField("modo", max_length=12, choices=Mode.choices, default=Mode.PRACTICE)
    kind = models.CharField("tipo", max_length=20, choices=Kind.choices, default=Kind.CUSTOM)
    status = models.CharField("estado", max_length=10, choices=Status.choices, default=Status.ACTIVE)
    chapter = models.ForeignKey(Chapter, verbose_name="capítulo", null=True, blank=True, on_delete=models.PROTECT)
    passage = models.ForeignKey("content.Passage", verbose_name="texto", null=True, blank=True, on_delete=models.PROTECT)
    parent = models.ForeignKey("self", verbose_name="sessão de origem", null=True, blank=True, on_delete=models.SET_NULL)
    filters = models.JSONField("filtros usados", default=dict, blank=True)
    title = models.CharField("título", max_length=200, blank=True)
    started_at = models.DateTimeField("iniciada em", default=timezone.now)
    last_activity_at = models.DateTimeField("última atividade", default=timezone.now)
    finished_at = models.DateTimeField("concluída em", null=True, blank=True)
    result_score = models.FloatField("resultado (0–1)", null=True, blank=True)

    class Meta:
        verbose_name = "sessão de estudo"
        verbose_name_plural = "sessões de estudo"
        ordering = ["-last_activity_at"]

    def __str__(self) -> str:
        return self.title or f"Sessão {self.pk}"

    def get_absolute_url(self) -> str:
        return reverse("learning:session_play", args=[self.pk])

    @property
    def is_assessment(self) -> bool:
        return self.mode == self.Mode.ASSESSMENT

    def total(self) -> int:
        return self.items.count()

    def answered_count(self) -> int:
        return self.items.filter(answered_at__isnull=False).count()

    def next_item(self):
        return self.items.filter(answered_at__isnull=True).order_by("position").first()


class SessionItem(models.Model):
    session = models.ForeignKey(StudySession, on_delete=models.CASCADE, related_name="items")
    exercise = models.ForeignKey(Exercise, on_delete=models.PROTECT, related_name="session_items")
    position = models.PositiveIntegerField()
    shown_at = models.DateTimeField(null=True, blank=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    attempt = models.OneToOneField("Attempt", null=True, blank=True, on_delete=models.SET_NULL, related_name="session_item")

    class Meta:
        ordering = ["session", "position"]
        constraints = [models.UniqueConstraint(fields=["session", "position"], name="uniq_session_position")]


class Attempt(models.Model):
    """Uma resposta. Nunca é alterada depois de gravada (ver ``save``)."""

    class Result(models.TextChoices):
        CORRECT = "correct", "Correta"
        PARTIAL = "partial", "Parcial"
        INCORRECT = "incorrect", "Incorreta"
        PENDING = "pending", "Aguardando avaliação"

    exercise = models.ForeignKey(Exercise, verbose_name="questão", on_delete=models.PROTECT, related_name="attempts")
    exercise_version = models.PositiveIntegerField("versão respondida")
    session = models.ForeignKey(StudySession, verbose_name="sessão", null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="attempts")
    mode = models.CharField("modo", max_length=12, choices=StudySession.Mode.choices, default=StudySession.Mode.PRACTICE)
    answer = models.JSONField("resposta enviada")
    answer_display = models.TextField("resposta (texto)")
    correct_display = models.TextField("resposta correta (na versão respondida)")
    result = models.CharField("resultado", max_length=10, choices=Result.choices)
    score = models.FloatField("pontuação", validators=[MinValueValidator(0), MaxValueValidator(1)])
    feedback = models.TextField("observação da correção", blank=True)
    duration_seconds = models.PositiveIntegerField("tempo de resposta (s)", default=0)
    used_translation = models.BooleanField("consultou a tradução", default=False)
    created_at = models.DateTimeField("respondida em", default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "tentativa"
        verbose_name_plural = "tentativas"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.exercise.code} — {self.get_result_display()}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError("Tentativas são imutáveis e não podem ser sobrescritas.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # pragma: no cover - proteção
        raise ValidationError("Tentativas fazem parte do histórico e não podem ser apagadas individualmente.")

    @property
    def is_correct(self) -> bool:
        return self.result == self.Result.CORRECT

    @property
    def effective_score(self) -> float | None:
        """Pontuação considerando autoavaliação/correção posterior da produção escrita."""
        if self.result != self.Result.PENDING:
            return self.score
        written = getattr(self, "written", None)
        if written and written.assessed_score is not None:
            return written.assessed_score
        return None


class WrittenAnswer(models.Model):
    """Produção escrita: texto livre + autoavaliação ou correção manual posterior."""

    attempt = models.OneToOneField(Attempt, on_delete=models.PROTECT, related_name="written")
    text = models.TextField("texto escrito")
    criteria_checked = models.JSONField("critérios atendidos", default=list, blank=True)
    assessed_score = models.FloatField("nota atribuída", null=True, blank=True,
                                       validators=[MinValueValidator(0), MaxValueValidator(1)])
    assessed_by = models.CharField("avaliado por", max_length=10, blank=True,
                                   choices=[("self", "Autoavaliação"), ("manual", "Correção manual")])
    assessed_at = models.DateTimeField("avaliado em", null=True, blank=True)
    marked_for_review = models.BooleanField("revisar depois", default=False)
    notes = models.TextField("anotações", blank=True)

    class Meta:
        verbose_name = "produção escrita"
        verbose_name_plural = "produções escritas"
        ordering = ["-attempt__created_at"]

    def __str__(self) -> str:
        return f"Texto de {self.attempt.created_at:%d/%m/%Y}"


class ReviewItem(models.Model):
    """Estado de revisão espaçada e do caderno de erros de uma questão."""

    INTERVALS = (1, 3, 7, 14, 30)

    class Recovery(models.TextChoices):
        RECENT = "recent", "Erro recente"
        REVIEWING = "reviewing", "Em revisão"
        IMPROVING = "improving", "Melhorando"
        OVERCOME = "overcome", "Superado"

    exercise = models.OneToOneField(Exercise, verbose_name="questão", on_delete=models.PROTECT, related_name="review_item")
    stage = models.PositiveSmallIntegerField("etapa", default=0)
    interval_days = models.PositiveIntegerField("intervalo (dias)", default=1)
    due_at = models.DateTimeField("próxima revisão", db_index=True)
    error_count = models.PositiveIntegerField("quantidade de erros", default=0)
    correct_streak = models.PositiveIntegerField("acertos seguidos", default=0)
    review_count = models.PositiveIntegerField("revisões feitas", default=0)
    last_result = models.CharField("último resultado", max_length=10, blank=True)
    last_answer = models.TextField("última resposta errada", blank=True)
    last_attempt_at = models.DateTimeField("última tentativa", null=True, blank=True)
    last_error_at = models.DateTimeField("último erro", null=True, blank=True)
    flagged = models.BooleanField("marcada pelo estudante", default=False)
    recovery = models.CharField("estado de recuperação", max_length=10, choices=Recovery.choices, blank=True)

    class Meta:
        verbose_name = "item de revisão"
        verbose_name_plural = "itens de revisão"
        ordering = ["due_at"]

    def __str__(self) -> str:
        return f"{self.exercise.code} (etapa {self.stage})"

    @property
    def in_notebook(self) -> bool:
        return self.error_count > 0

    @property
    def is_due(self) -> bool:
        return self.due_at <= timezone.now()


class Mastery(models.Model):
    """Domínio calculado (cache) para um escopo: capítulo, objetivo, gramática, vocabulário ou competência."""

    class Scope(models.TextChoices):
        OVERALL = "overall", "Geral"
        CHAPTER = "chapter", "Capítulo"
        OBJECTIVE = "objective", "Objetivo"
        GRAMMAR = "grammar", "Gramática"
        VOCABULARY = "vocabulary", "Vocabulário"
        COMPETENCY = "competency", "Competência"

    scope = models.CharField("escopo", max_length=12, choices=Scope.choices)
    object_id = models.PositiveIntegerField("id do objeto", default=0)
    label = models.CharField("nome", max_length=300)
    score = models.FloatField("domínio (0–100)")
    details = models.JSONField("componentes do cálculo", default=dict)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "domínio"
        verbose_name_plural = "domínios"
        constraints = [models.UniqueConstraint(fields=["scope", "object_id"], name="uniq_mastery_scope")]
        ordering = ["scope", "-score"]

    def __str__(self) -> str:
        return f"{self.label}: {self.score:.0f}%"


class UserSetting(models.Model):
    """Preferências do estudante (registro único)."""

    class FontSize(models.TextChoices):
        NORMAL = "normal", "Normal"
        LARGE = "large", "Grande"
        XLARGE = "xlarge", "Muito grande"

    class Theme(models.TextChoices):
        AUTO = "auto", "Seguir o sistema"
        LIGHT = "light", "Claro"
        DARK = "dark", "Escuro"

    display_name = models.CharField("como chamar você", max_length=60, blank=True)
    default_session_size = models.PositiveSmallIntegerField("questões por sessão", default=10,
                                                            validators=[MinValueValidator(3), MaxValueValidator(50)])
    daily_goal_minutes = models.PositiveSmallIntegerField("meta diária (min)", default=20,
                                                          validators=[MinValueValidator(5), MaxValueValidator(240)])
    show_keyboard = models.BooleanField("mostrar teclado de acentos", default=True)
    font_size = models.CharField("tamanho do texto", max_length=10, choices=FontSize.choices, default=FontSize.NORMAL)
    theme = models.CharField("tema visual", max_length=10, choices=Theme.choices, default=Theme.AUTO)
    current_chapter = models.ForeignKey(Chapter, verbose_name="capítulo atual", null=True, blank=True,
                                        on_delete=models.SET_NULL)

    class Meta:
        verbose_name = "preferências"
        verbose_name_plural = "preferências"

    def __str__(self) -> str:
        return "Preferências"

    @classmethod
    def get(cls) -> "UserSetting":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

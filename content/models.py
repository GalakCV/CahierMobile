"""
Modelos de conteúdo pedagógico.

Organização:
    Course → Chapter → (LearningObjective, GrammarTopic, VocabularyTopic, Passage, Exercise)
    Exercise → Choice, AcceptedAnswer, ExerciseVersion, ExerciseRelation
    Source registra autoria e licença de qualquer conteúdo.

Regras de preservação:
- Nada é apagado no uso normal: conteúdos são desativados (``is_active=False``).
- Cada alteração de conteúdo de uma questão gera uma ``ExerciseVersion`` com um
  retrato completo (enunciado, alternativas, respostas, explicação).
- As tentativas (app ``learning``) apontam para a versão respondida.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.urls import reverse

CEFR_LEVELS = [(lvl, lvl) for lvl in ("A1", "A2", "B1", "B2")]
code_validator_re = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def validate_code(value: str) -> None:
    if not code_validator_re.match(value or ""):
        raise ValidationError("Use apenas letras minúsculas, números, ponto, hífen ou sublinhado.")


class TimeStamped(models.Model):
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        abstract = True


class Origin(models.TextChoices):
    ORIGINAL = "original", "Original"
    ADAPTED = "adapted", "Adaptada"
    OER = "oer", "Recurso educacional aberto"
    PUBLIC_DOMAIN = "public_domain", "Domínio público"
    EXAM_INSPIRED = "exam_inspired", "Inspirada em formato de exame"


class Source(TimeStamped):
    """Fonte, autoria e licença. Toda questão e todo texto apontam para uma fonte."""

    key = models.SlugField("identificador", max_length=60, unique=True)
    title = models.CharField("título", max_length=200)
    author = models.CharField("autoria", max_length=200)
    url = models.URLField("URL", blank=True)
    license_name = models.CharField("licença", max_length=120)
    license_url = models.URLField("URL da licença", blank=True)
    notes = models.TextField("observações de uso e adaptação", blank=True)

    class Meta:
        verbose_name = "fonte"
        verbose_name_plural = "fontes"
        ordering = ["title"]

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("content:source_detail", args=[self.key])


class Course(TimeStamped):
    code = models.CharField("código", max_length=40, unique=True, validators=[validate_code])
    title = models.CharField("título", max_length=200)
    description = models.TextField("descrição", blank=True)
    reference_source = models.ForeignKey(Source, verbose_name="referência curricular", null=True,
                                         blank=True, on_delete=models.PROTECT)

    class Meta:
        verbose_name = "curso"
        verbose_name_plural = "cursos"

    def __str__(self) -> str:
        return self.title


class Competency(TimeStamped):
    """Competência avaliada (vocabulário, gramática, leitura, interpretação, escrita…)."""

    code = models.CharField("código", max_length=40, unique=True, validators=[validate_code])
    name = models.CharField("nome", max_length=120)
    description = models.TextField("descrição", blank=True)
    position = models.PositiveIntegerField("ordem", default=0)

    class Meta:
        verbose_name = "competência"
        verbose_name_plural = "competências"
        ordering = ["position", "name"]

    def __str__(self) -> str:
        return self.name


class Chapter(TimeStamped):
    course = models.ForeignKey(Course, verbose_name="curso", on_delete=models.PROTECT, related_name="chapters")
    code = models.CharField("código", max_length=40, unique=True, validators=[validate_code])
    number = models.PositiveIntegerField("número")
    title = models.CharField("título", max_length=200)
    theme = models.CharField("tema", max_length=200)
    description = models.TextField("descrição")
    cefr_level = models.CharField("nível CEFR", max_length=2, choices=CEFR_LEVELS, default="A1")
    useful_expressions = models.JSONField("expressões úteis", default=list, blank=True,
                                          help_text='Lista de {"fr": "...", "pt": "..."}')
    review_summary = models.TextField("resumo de revisão", blank=True,
                                      help_text="Uma linha por ponto a revisar.")
    reference_note = models.TextField("relação com a referência curricular", blank=True)
    is_active = models.BooleanField("ativo", default=True)
    is_planned = models.BooleanField("planejado (sem conteúdo ainda)", default=False)

    class Meta:
        verbose_name = "capítulo"
        verbose_name_plural = "capítulos"
        ordering = ["course", "number"]
        constraints = [models.UniqueConstraint(fields=["course", "number"], name="uniq_chapter_number")]

    def __str__(self) -> str:
        return f"{self.number}. {self.title}"

    def get_absolute_url(self) -> str:
        return reverse("content:chapter_detail", args=[self.code])

    def review_points(self) -> list[str]:
        return [ln.strip() for ln in self.review_summary.splitlines() if ln.strip()]


class LearningObjective(TimeStamped):
    chapter = models.ForeignKey(Chapter, verbose_name="capítulo", on_delete=models.PROTECT, related_name="objectives")
    code = models.CharField("código", max_length=60, unique=True, validators=[validate_code])
    description = models.CharField("objetivo (\"Eu consigo…\")", max_length=300)
    competencies = models.ManyToManyField(Competency, verbose_name="competências", blank=True)
    position = models.PositiveIntegerField("ordem", default=0)
    is_active = models.BooleanField("ativo", default=True)

    class Meta:
        verbose_name = "objetivo de aprendizagem"
        verbose_name_plural = "objetivos de aprendizagem"
        ordering = ["chapter", "position", "id"]

    def __str__(self) -> str:
        return self.description


class GrammarTopic(TimeStamped):
    """Tópico gramatical com explicação curta, exemplos, tabelas e erros frequentes."""

    chapter = models.ForeignKey(Chapter, verbose_name="capítulo", on_delete=models.PROTECT, related_name="grammar_topics")
    code = models.CharField("código", max_length=60, unique=True, validators=[validate_code])
    title = models.CharField("título", max_length=200)
    summary = models.TextField("explicação resumida")
    examples = models.JSONField("exemplos", default=list, blank=True, help_text='Lista de {"fr": "...", "pt": "..."}')
    tables = models.JSONField("tabelas de conjugação", default=list, blank=True,
                              help_text='Lista de {"title": "être (presente)", "rows": [["je", "suis"], ...]}')
    notes = models.TextField("observações gramaticais", blank=True)
    common_errors = models.JSONField("erros frequentes de falantes de português", default=list, blank=True,
                                     help_text='Lista de {"wrong": "...", "right": "...", "why": "..."}')
    position = models.PositiveIntegerField("ordem", default=0)
    is_active = models.BooleanField("ativo", default=True)

    class Meta:
        verbose_name = "tópico gramatical"
        verbose_name_plural = "tópicos gramaticais"
        ordering = ["chapter", "position", "id"]

    def __str__(self) -> str:
        return self.title


class VocabularyTopic(TimeStamped):
    chapter = models.ForeignKey(Chapter, verbose_name="capítulo", on_delete=models.PROTECT, related_name="vocabulary_topics")
    code = models.CharField("código", max_length=60, unique=True, validators=[validate_code])
    title = models.CharField("título", max_length=200)
    position = models.PositiveIntegerField("ordem", default=0)
    is_active = models.BooleanField("ativo", default=True)

    class Meta:
        verbose_name = "tema de vocabulário"
        verbose_name_plural = "temas de vocabulário"
        ordering = ["chapter", "position", "id"]

    def __str__(self) -> str:
        return self.title


class VocabularyItem(models.Model):
    topic = models.ForeignKey(VocabularyTopic, verbose_name="tema", on_delete=models.CASCADE, related_name="items")
    french = models.CharField("francês", max_length=200)
    portuguese = models.CharField("português", max_length=200)
    gender = models.CharField("gênero", max_length=10, blank=True, help_text="m, f, m/f, pl…")
    example = models.CharField("exemplo", max_length=300, blank=True)
    position = models.PositiveIntegerField("ordem", default=0)

    class Meta:
        verbose_name = "palavra"
        verbose_name_plural = "palavras"
        ordering = ["topic", "position", "id"]

    def __str__(self) -> str:
        return f"{self.french} — {self.portuguese}"


class ReviewStatus(models.TextChoices):
    DRAFT = "draft", "Rascunho"
    REVIEWED = "reviewed", "Revisada"
    NEEDS_FIX = "needs_fix", "Precisa de correção"


class Passage(TimeStamped):
    """Texto para compreensão escrita e interpretação."""

    class TextType(models.TextChoices):
        PRESENTATION = "presentation", "Apresentação pessoal"
        PROFILE = "profile", "Perfil"
        MESSAGE = "message", "Mensagem"
        EMAIL = "email", "E-mail"
        AD = "ad", "Anúncio"
        MENU = "menu", "Cardápio"
        SCHEDULE = "schedule", "Horário"
        INVITATION = "invitation", "Convite"
        FORM = "form", "Formulário"
        DIALOGUE = "dialogue", "Diálogo"
        DESCRIPTION = "description", "Descrição"
        ROUTINE = "routine", "Rotina"
        NARRATIVE = "narrative", "Pequena narrativa"
        CITY = "city", "Informações sobre cidade"
        OTHER = "other", "Outro"

    chapter = models.ForeignKey(Chapter, verbose_name="capítulo", on_delete=models.PROTECT, related_name="passages")
    code = models.CharField("código", max_length=60, unique=True, validators=[validate_code])
    title = models.CharField("título", max_length=200)
    text_type = models.CharField("tipo de texto", max_length=20, choices=TextType.choices)
    body = models.TextField("texto", help_text="Linhas em branco separam parágrafos. Em diálogos, use 'Nome : fala'.")
    translation_pt = models.TextField("tradução de apoio", blank=True)
    cefr_level = models.CharField("nível CEFR", max_length=2, choices=CEFR_LEVELS, default="A1")
    difficulty = models.PositiveSmallIntegerField("dificuldade", validators=[MinValueValidator(1), MaxValueValidator(5)])
    key_vocabulary = models.JSONField("vocabulário principal", default=list, blank=True,
                                      help_text='Lista de {"fr": "...", "pt": "..."}')
    useful_structures = models.JSONField("estruturas úteis", default=list, blank=True,
                                         help_text='Lista de {"fr": "...", "pt": "..."}')
    grammar_topics = models.ManyToManyField(GrammarTopic, verbose_name="tópicos gramaticais", blank=True)
    vocabulary_topics = models.ManyToManyField(VocabularyTopic, verbose_name="temas de vocabulário", blank=True)
    author = models.CharField("autoria", max_length=200)
    source = models.ForeignKey(Source, verbose_name="fonte", on_delete=models.PROTECT, related_name="passages")
    origin = models.CharField("origem", max_length=20, choices=Origin.choices, default=Origin.ORIGINAL)
    adaptation_notes = models.TextField("observações de adaptação", blank=True)
    review_status = models.CharField("revisão pedagógica", max_length=12, choices=ReviewStatus.choices,
                                     default=ReviewStatus.DRAFT)
    position = models.PositiveIntegerField("ordem", default=0)
    is_active = models.BooleanField("ativo", default=True)

    class Meta:
        verbose_name = "texto"
        verbose_name_plural = "textos"
        ordering = ["chapter", "position", "id"]

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("content:passage_detail", args=[self.code])

    @property
    def word_count(self) -> int:
        text = re.sub(r"^[^:\n]{1,30} :", "", self.body, flags=re.M)  # ignora rótulos de falantes
        return len(re.findall(r"[\wÀ-ÿœæŒÆ'’-]+", text))

    def paragraphs(self) -> list[str]:
        return [p.strip() for p in re.split(r"\n\s*\n", self.body) if p.strip()]


class Exercise(TimeStamped):
    """Questão. O ``exercise_type`` é pedagógico; ``interaction`` define como é respondida."""

    class Type(models.TextChoices):
        MC_SINGLE = "mc_single", "Múltipla escolha"
        MC_MULTIPLE = "mc_multiple", "Múltipla seleção"
        TRUE_FALSE = "true_false", "Verdadeiro ou falso"
        FILL_BLANK = "fill_blank", "Completar lacunas"
        ORDER_WORDS = "order_words", "Ordenar palavras"
        ORDER_SENTENCES = "order_sentences", "Ordenar frases"
        MATCH_PAIRS = "match_pairs", "Relacionar pares"
        CONJUGATION = "conjugation", "Conjugação verbal"
        SELECT_ARTICLE = "select_article", "Selecionar artigo"
        SELECT_PRONOUN = "select_pronoun", "Selecionar pronome"
        SELECT_PREPOSITION = "select_preposition", "Selecionar preposição"
        SELECT_VERB_FORM = "select_verb_form", "Selecionar forma verbal"
        IDENTIFY_ERROR = "identify_error", "Identificar erro"
        CORRECT_SENTENCE = "correct_sentence", "Corrigir frase"
        TRANSFORM_NEGATIVE = "transform_negative", "Transformar em negativa"
        TRANSFORM_QUESTION = "transform_question", "Transformar em pergunta"
        TRANSFORM_PLURAL = "transform_plural", "Passar para o plural"
        TRANSFORM_GENDER = "transform_gender", "Alterar o gênero"
        TRANSLATE_FR_PT = "translate_fr_pt", "Tradução francês → português"
        TRANSLATE_PT_FR = "translate_pt_fr", "Tradução português → francês"
        DIALOGUE_COMPREHENSION = "dialogue_comprehension", "Compreensão de diálogo escrito"
        TEXT_INTERPRETATION = "text_interpretation", "Interpretação de texto"
        SHORT_ANSWER = "short_answer", "Resposta curta"
        GUIDED_WRITING = "guided_writing", "Produção escrita guiada"
        VOCABULARY_REVIEW = "vocabulary_review", "Revisão de vocabulário"
        COMPLETE_DIALOGUE = "complete_dialogue", "Completar diálogo"
        NATURAL_RESPONSE = "natural_response", "Resposta mais natural"

    class Interaction(models.TextChoices):
        SINGLE = "single", "Escolha única"
        MULTIPLE = "multiple", "Escolha múltipla"
        TEXT = "text", "Resposta digitada"
        ORDER = "order", "Ordenação"
        MATCH = "match", "Relacionar"
        WRITING = "writing", "Texto livre"

    class Comparison(models.TextChoices):
        EXACT = "exact", "Exato"
        NORMALIZED = "normalized", "Normalizado"
        ACCEPTED_LIST = "accepted_list", "Lista de respostas aceitas"
        REGEX = "regex", "Expressão regular"
        MANUAL = "manual", "Correção manual"
        SELF = "self", "Autoavaliação"

    class ReadingSkill(models.TextChoices):
        EXPLICIT = "explicit", "Localizar informação explícita"
        THEME = "theme", "Identificar tema"
        CHARACTER = "character", "Identificar personagem"
        PLACE = "place", "Identificar local"
        TIME = "time", "Identificar data ou horário"
        TRUE_FALSE = "true_false", "Verdadeiro ou falso"
        SEQUENCE = "sequence", "Ordenar acontecimentos"
        MEANING = "meaning", "Significado pelo contexto"
        SUMMARY = "summary", "Escolher o melhor resumo"
        RELATE = "relate", "Relacionar informações"
        INFERENCE = "inference", "Inferência simples"
        SHORT = "short", "Resposta curta"
        COMPLETE = "complete", "Completar informação"
        INTENT = "intent", "Intenção da mensagem"

    # Quais interações cada tipo aceita (a primeira é a padrão).
    TYPE_INTERACTIONS: dict[str, tuple[str, ...]] = {
        "mc_single": ("single",),
        "mc_multiple": ("multiple",),
        "true_false": ("single",),
        "fill_blank": ("text",),
        "order_words": ("order",),
        "order_sentences": ("order",),
        "match_pairs": ("match",),
        "conjugation": ("text", "single"),
        "select_article": ("single",),
        "select_pronoun": ("single",),
        "select_preposition": ("single",),
        "select_verb_form": ("single",),
        "identify_error": ("single",),
        "correct_sentence": ("text",),
        "transform_negative": ("text",),
        "transform_question": ("text",),
        "transform_plural": ("text",),
        "transform_gender": ("text",),
        "translate_fr_pt": ("text", "single"),
        "translate_pt_fr": ("text", "single"),
        "dialogue_comprehension": ("single", "multiple", "text", "order"),
        "text_interpretation": ("single", "multiple", "text", "order", "match"),
        "short_answer": ("text",),
        "guided_writing": ("writing",),
        "vocabulary_review": ("text", "single", "match"),
        "complete_dialogue": ("text", "single"),
        "natural_response": ("single",),
    }

    BLANK = "___"

    chapter = models.ForeignKey(Chapter, verbose_name="capítulo", on_delete=models.PROTECT, related_name="exercises")
    passage = models.ForeignKey(Passage, verbose_name="texto associado", null=True, blank=True,
                                on_delete=models.PROTECT, related_name="exercises")
    code = models.CharField("código", max_length=80, unique=True, validators=[validate_code])
    exercise_type = models.CharField("tipo de exercício", max_length=30, choices=Type.choices)
    interaction = models.CharField("forma de resposta", max_length=10, choices=Interaction.choices)
    instruction = models.CharField("instrução (português)", max_length=300)
    prompt = models.TextField("enunciado", help_text="Use ___ para cada lacuna.")
    context = models.TextField("contexto (diálogo, situação)", blank=True)
    translation_pt = models.TextField("tradução de apoio", blank=True)
    explanation = models.TextField("explicação pedagógica")
    evidence = models.TextField("trecho que fundamenta a resposta", blank=True)
    model_answer = models.TextField("resposta-modelo", blank=True)
    criteria = models.JSONField("critérios de avaliação", default=list, blank=True,
                                help_text="Lista de critérios (produção escrita).")
    difficulty = models.PositiveSmallIntegerField("dificuldade", validators=[MinValueValidator(1), MaxValueValidator(5)])
    cefr_level = models.CharField("nível CEFR", max_length=2, choices=CEFR_LEVELS, default="A1")
    estimated_seconds = models.PositiveIntegerField("tempo estimado (s)", default=45)
    competency = models.ForeignKey(Competency, verbose_name="competência", on_delete=models.PROTECT, related_name="exercises")
    objectives = models.ManyToManyField(LearningObjective, verbose_name="objetivos", blank=True, related_name="exercises")
    grammar_topics = models.ManyToManyField(GrammarTopic, verbose_name="tópicos gramaticais", blank=True, related_name="exercises")
    vocabulary_topics = models.ManyToManyField(VocabularyTopic, verbose_name="temas de vocabulário", blank=True, related_name="exercises")
    comparison_mode = models.CharField("modo de comparação", max_length=15, choices=Comparison.choices,
                                       default=Comparison.ACCEPTED_LIST)
    accent_insensitive = models.BooleanField(
        "tolerar acentos", default=False,
        help_text="Só marque quando acentos NÃO forem o objeto do exercício (ex.: tradução para o português).")
    reading_skill = models.CharField("habilidade de leitura", max_length=12, choices=ReadingSkill.choices, blank=True)
    is_assessment = models.BooleanField("faz parte da avaliação do capítulo", default=False)
    origin = models.CharField("origem", max_length=20, choices=Origin.choices, default=Origin.ORIGINAL)
    source = models.ForeignKey(Source, verbose_name="fonte", on_delete=models.PROTECT, related_name="exercises")
    adaptation_notes = models.TextField("observações de adaptação", blank=True)
    review_status = models.CharField("revisão pedagógica", max_length=12, choices=ReviewStatus.choices,
                                     default=ReviewStatus.DRAFT)
    is_active = models.BooleanField("ativa", default=True)
    version = models.PositiveIntegerField("versão atual", default=0, editable=False)
    position = models.PositiveIntegerField("ordem", default=0)

    class Meta:
        verbose_name = "questão"
        verbose_name_plural = "questões"
        ordering = ["chapter", "position", "id"]
        indexes = [models.Index(fields=["chapter", "is_active", "difficulty"])]

    def __str__(self) -> str:
        return f"[{self.code}] {self.get_exercise_type_display()}"

    # ----- validação -----
    def clean(self) -> None:
        errors: dict[str, str] = {}
        allowed = self.TYPE_INTERACTIONS.get(self.exercise_type, ())
        if self.interaction and allowed and self.interaction not in allowed:
            labels = ", ".join(dict(self.Interaction.choices)[i] for i in allowed)
            errors["interaction"] = f"Este tipo aceita apenas: {labels}."
        if self.interaction == self.Interaction.WRITING and self.comparison_mode not in (
                self.Comparison.SELF, self.Comparison.MANUAL):
            errors["comparison_mode"] = "Produção escrita usa autoavaliação ou correção manual."
        if self.interaction == self.Interaction.WRITING and not self.model_answer:
            errors["model_answer"] = "Produção escrita precisa de resposta-modelo."
        if self.passage_id and self.chapter_id and self.passage.chapter_id != self.chapter_id:
            errors["passage"] = "O texto deve pertencer ao mesmo capítulo."
        if self.origin == Origin.ADAPTED and not self.adaptation_notes:
            errors["adaptation_notes"] = "Descreva a adaptação feita."
        if errors:
            raise ValidationError(errors)

    # ----- utilidades -----
    @property
    def blank_count(self) -> int:
        return self.prompt.count(self.BLANK) if self.interaction == self.Interaction.TEXT else 0

    def prompt_parts(self) -> list[str]:
        """Divide o enunciado nas lacunas para renderizar campos inline."""
        return self.prompt.split(self.BLANK)

    def criteria_list(self) -> list[str]:
        return [c for c in (self.criteria or []) if str(c).strip()]

    def get_absolute_url(self) -> str:
        return reverse("content:exercise_preview", args=[self.code])

    # ----- versões -----
    def content_snapshot(self) -> dict:
        """Retrato completo do conteúdo avaliável da questão."""
        return {
            "code": self.code,
            "exercise_type": self.exercise_type,
            "interaction": self.interaction,
            "instruction": self.instruction,
            "prompt": self.prompt,
            "context": self.context,
            "translation_pt": self.translation_pt,
            "explanation": self.explanation,
            "evidence": self.evidence,
            "model_answer": self.model_answer,
            "criteria": self.criteria,
            "difficulty": self.difficulty,
            "comparison_mode": self.comparison_mode,
            "accent_insensitive": self.accent_insensitive,
            "choices": [
                {"id": c.pk, "text": c.text, "is_correct": c.is_correct,
                 "correct_position": c.correct_position, "match_text": c.match_text, "position": c.position}
                for c in self.choices.all().order_by("position", "id")
            ],
            "answers": [
                {"text": a.text, "blank_index": a.blank_index, "is_primary": a.is_primary}
                for a in self.accepted_answers.all().order_by("blank_index", "-is_primary", "id")
            ],
        }

    @transaction.atomic
    def snapshot_version(self, note: str = "") -> "ExerciseVersion":
        """Cria nova versão se o conteúdo mudou; devolve a versão atual."""
        snap = self.content_snapshot()
        digest = hashlib.sha256(json.dumps(snap, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        latest = self.versions.order_by("-number").first()
        if latest and latest.content_hash == digest:
            return latest
        number = (latest.number if latest else 0) + 1
        version = ExerciseVersion.objects.create(exercise=self, number=number, snapshot=snap,
                                                 content_hash=digest, note=note)
        Exercise.objects.filter(pk=self.pk).update(version=number)
        self.version = number
        return version

    def current_version(self) -> "ExerciseVersion":
        return self.versions.order_by("-number").first() or self.snapshot_version("versão inicial")


class Choice(models.Model):
    """Alternativa. ``position`` garante ordem estável de exibição.

    - escolha única/múltipla: ``is_correct``
    - ordenação: ``correct_position`` (1, 2, 3…); ``position`` é a ordem embaralhada exibida
    - relacionar: ``text`` (coluna da esquerda) ↔ ``match_text`` (coluna da direita)
    """

    exercise = models.ForeignKey(Exercise, verbose_name="questão", on_delete=models.CASCADE, related_name="choices")
    text = models.CharField("texto", max_length=400)
    is_correct = models.BooleanField("correta", default=False)
    correct_position = models.PositiveIntegerField("posição correta (ordenação)", null=True, blank=True)
    match_text = models.CharField("par correspondente (relacionar)", max_length=400, blank=True)
    feedback = models.CharField("comentário sobre esta alternativa", max_length=400, blank=True)
    position = models.PositiveIntegerField("ordem de exibição", default=0)

    class Meta:
        verbose_name = "alternativa"
        verbose_name_plural = "alternativas"
        ordering = ["exercise", "position", "id"]

    def __str__(self) -> str:
        return self.text


class AcceptedAnswer(models.Model):
    exercise = models.ForeignKey(Exercise, verbose_name="questão", on_delete=models.CASCADE, related_name="accepted_answers")
    text = models.CharField("resposta", max_length=500)
    blank_index = models.PositiveSmallIntegerField("lacuna", default=0, help_text="0 para a primeira lacuna (ou resposta única).")
    is_primary = models.BooleanField("resposta principal", default=True,
                                     help_text="As principais são exibidas como resposta correta.")

    class Meta:
        verbose_name = "resposta aceita"
        verbose_name_plural = "respostas aceitas"
        ordering = ["exercise", "blank_index", "-is_primary", "id"]

    def __str__(self) -> str:
        return self.text

    def clean(self) -> None:
        if self.exercise_id and self.exercise.comparison_mode == Exercise.Comparison.REGEX:
            try:
                re.compile(self.text)
            except re.error as exc:
                raise ValidationError({"text": f"Expressão regular inválida: {exc}"})


class ExerciseVersion(models.Model):
    """Retrato imutável de uma versão da questão."""

    exercise = models.ForeignKey(Exercise, verbose_name="questão", on_delete=models.CASCADE, related_name="versions")
    number = models.PositiveIntegerField("número")
    snapshot = models.JSONField("conteúdo")
    content_hash = models.CharField(max_length=64)
    note = models.CharField("nota", max_length=200, blank=True)
    created_at = models.DateTimeField("criada em", auto_now_add=True)

    class Meta:
        verbose_name = "versão de questão"
        verbose_name_plural = "versões de questões"
        ordering = ["exercise", "-number"]
        constraints = [models.UniqueConstraint(fields=["exercise", "number"], name="uniq_exercise_version")]

    def __str__(self) -> str:
        return f"{self.exercise.code} v{self.number}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Versões de questões são imutáveis.")
        super().save(*args, **kwargs)


class ExerciseRelation(models.Model):
    class Kind(models.TextChoices):
        SIMILAR = "similar", "Muito semelhante (evitar na mesma sessão)"
        VARIANT = "variant", "Variante da mesma questão"
        PREREQUISITE = "prerequisite", "Pré-requisito"
        FOLLOW_UP = "follow_up", "Continuação"

    from_exercise = models.ForeignKey(Exercise, verbose_name="questão", on_delete=models.CASCADE, related_name="relations_from")
    to_exercise = models.ForeignKey(Exercise, verbose_name="relacionada a", on_delete=models.CASCADE, related_name="relations_to")
    kind = models.CharField("tipo de relação", max_length=15, choices=Kind.choices, default=Kind.SIMILAR)

    class Meta:
        verbose_name = "relação entre questões"
        verbose_name_plural = "relações entre questões"
        constraints = [models.UniqueConstraint(fields=["from_exercise", "to_exercise", "kind"], name="uniq_ex_relation")]

    def __str__(self) -> str:
        return f"{self.from_exercise.code} → {self.to_exercise.code} ({self.kind})"

    def clean(self) -> None:
        if self.from_exercise_id and self.from_exercise_id == self.to_exercise_id:
            raise ValidationError("Uma questão não pode se relacionar com ela mesma.")


class ContentIssue(TimeStamped):
    """Problema sinalizado pelo estudante (ambiguidade, erro de francês…)."""

    class Kind(models.TextChoices):
        AMBIGUOUS = "ambiguous", "Questão ambígua"
        WRONG_ANSWER = "wrong_answer", "Resposta correta parece errada"
        FRENCH_ERROR = "french_error", "Erro no francês"
        EXPLANATION = "explanation", "Explicação confusa"
        OTHER = "other", "Outro"

    class Status(models.TextChoices):
        OPEN = "open", "Aberto"
        RESOLVED = "resolved", "Resolvido"
        DISMISSED = "dismissed", "Descartado"

    exercise = models.ForeignKey(Exercise, verbose_name="questão", on_delete=models.PROTECT, related_name="issues")
    exercise_version = models.PositiveIntegerField("versão sinalizada", default=0)
    kind = models.CharField("tipo", max_length=15, choices=Kind.choices)
    comment = models.TextField("comentário", blank=True, max_length=2000)
    user_answer = models.TextField("resposta dada", blank=True)
    status = models.CharField("estado", max_length=10, choices=Status.choices, default=Status.OPEN)
    uid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    resolution_note = models.TextField("nota de resolução", blank=True)

    class Meta:
        verbose_name = "problema sinalizado"
        verbose_name_plural = "problemas sinalizados"
        ordering = ["status", "-created_at"]

    def __str__(self) -> str:
        return f"{self.exercise.code}: {self.get_kind_display()}"

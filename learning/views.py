"""Páginas de estudo: painel, sessões, revisão, caderno de erros, produção escrita, progresso."""
from __future__ import annotations

import random

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from content.models import Chapter, Competency, Exercise, Passage

from . import mastery, review, sessions, stats
from .forms import IssueForm, SessionForm, SettingsForm
from .models import Attempt, Mastery, ReviewItem, SessionItem, StudySession, UserSetting, WrittenAnswer


# ---------------------------------------------------------------------------
# Painel
# ---------------------------------------------------------------------------

def dashboard(request):
    data = stats.overview()
    current = data["current_chapter"]
    chapter_info = sessions.chapter_status(current) if current else None
    setting = UserSetting.get()
    goal = setting.daily_goal_minutes
    return render(request, "learning/dashboard.html", {
        **data,
        "chapter_info": chapter_info,
        "resume": sessions.resumable_session(),
        "goal_pct": min(100, round(100 * data["minutes_today"] / goal)) if goal else 0,
        "has_content": Exercise.objects.filter(is_active=True).exists(),
    })


# ---------------------------------------------------------------------------
# Criação de sessões
# ---------------------------------------------------------------------------

@require_http_methods(["GET", "POST"])
def session_new(request):
    initial = {}
    if request.GET.get("capitulo"):
        ch = Chapter.objects.filter(code=request.GET["capitulo"], is_active=True).first()
        if ch:
            initial["chapter"] = ch
    form = SessionForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        cd = form.cleaned_data
        assessment = cd["mode"] == StudySession.Mode.ASSESSMENT
        exercises = sessions.select_practice(
            chapter=cd["chapter"], topic=cd["topic"], competency=cd["competency"],
            difficulties=cd["difficulties"], count=cd["count"], include_assessment=assessment,
            seed=random.randrange(1_000_000))
        if not exercises:
            form.add_error(None, "Nenhuma questão encontrada com esses filtros. Experimente ampliar a seleção.")
        else:
            title = "Prática" if not assessment else "Avaliação"
            if cd["chapter"]:
                title += f" — {cd['chapter'].title}"
            filters = {"chapter": cd["chapter"].code if cd["chapter"] else None, "topic": cd["topic"],
                       "competency": cd["competency"].code if cd["competency"] else None,
                       "difficulties": cd["difficulties"], "count": cd["count"]}
            s = sessions.create_session(exercises, mode=cd["mode"], chapter=cd["chapter"], filters=filters,
                                        title=title)
            if len(exercises) < cd["count"]:
                messages.info(request, f"Foram encontradas {len(exercises)} questões com esses filtros.")
            return redirect(s)
    return render(request, "learning/session_new.html", {"form": form, "resume": sessions.resumable_session()})


@require_POST
def start_chapter_review(request, code):
    chapter = get_object_or_404(Chapter, code=code, is_active=True)
    exs = sessions.select_chapter_review(chapter, UserSetting.get().default_session_size + 2,
                                         seed=random.randrange(1_000_000))
    return _start(request, exs, kind=StudySession.Kind.CHAPTER_REVIEW, chapter=chapter,
                  title=f"Revisão — {chapter.title}")


@require_POST
def start_chapter_assessment(request, code):
    chapter = get_object_or_404(Chapter, code=code, is_active=True)
    return _start(request, sessions.select_chapter_assessment(chapter), mode=StudySession.Mode.ASSESSMENT,
                  kind=StudySession.Kind.CHAPTER_ASSESSMENT, chapter=chapter,
                  title=f"Avaliação final — {chapter.title}")


@require_POST
def start_passage(request, code):
    passage = get_object_or_404(Passage, code=code, is_active=True)
    mode = request.POST.get("mode") if request.POST.get("mode") in StudySession.Mode.values else "practice"
    return _start(request, sessions.select_passage(passage), mode=mode, kind=StudySession.Kind.PASSAGE,
                  chapter=passage.chapter, passage=passage, title=f"Texto — {passage.title}")


@require_POST
def start_spaced_review(request):
    exs = sessions.select_review(count=int(request.POST.get("count") or 15))
    if not exs:
        messages.success(request, "Nenhuma revisão pendente agora. Volte mais tarde!")
        return redirect("learning:review_queue")
    return _start(request, exs, kind=StudySession.Kind.SPACED_REVIEW, title="Revisões pendentes")


@require_POST
def session_retry(request, pk):
    parent = get_object_or_404(StudySession, pk=pk)
    exs = sessions.wrong_exercises(parent)
    if not exs:
        messages.success(request, "Não há questões erradas nesta sessão.")
        return redirect("learning:session_result", pk=pk)
    return _start(request, exs, kind=StudySession.Kind.RETRY, chapter=parent.chapter, passage=parent.passage,
                  parent=parent, title=f"Refazer erradas — {parent}")


def _start(request, exercises, **kwargs):
    try:
        s = sessions.create_session(exercises, **kwargs)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect(request.META.get("HTTP_REFERER") or "learning:dashboard")
    return redirect(s)


# ---------------------------------------------------------------------------
# Jogando a sessão
# ---------------------------------------------------------------------------

def _exercise_context(item: SessionItem) -> dict:
    ex = item.exercise
    choices = list(ex.choices.all().order_by("position", "id"))
    ctx = {"item": item, "ex": ex, "choices": choices}
    if ex.interaction == "match":
        rights = choices[:]
        random.Random(f"match-{ex.pk}").shuffle(rights)
        ctx["rights"] = rights
    if ex.interaction == "text":
        parts = ex.prompt_parts()
        ctx["prompt_parts"] = [(i, part, i < len(parts) - 1) for i, part in enumerate(parts)]
    return ctx


@require_http_methods(["GET", "POST"])
def session_play(request, pk):
    s = get_object_or_404(StudySession, pk=pk)
    if s.status == StudySession.Status.FINISHED:
        return redirect("learning:session_result", pk=pk)
    item = s.next_item()
    if item is None:
        sessions.finish(s)
        return redirect("learning:session_result", pk=pk)
    if s.status == StudySession.Status.PAUSED and request.method == "GET":
        s.status = StudySession.Status.ACTIVE
        s.save(update_fields=["status"])
    error = None
    if request.method == "POST":
        if str(item.pk) != request.POST.get("item"):
            messages.info(request, "Esta questão já tinha sido respondida; mostramos a próxima.")
            return redirect(s)
        from .grading import answer_is_empty, parse_answer
        if answer_is_empty(item.exercise, parse_answer(item.exercise, request.POST)):
            error = "Escreva ou selecione uma resposta antes de enviar."
        else:
            sessions.answer_item(item, request.POST, used_translation=request.POST.get("used_translation") == "1")
            if s.is_assessment:
                return redirect(s)
            return redirect("learning:session_feedback", pk=pk, pos=item.position)
    sessions.mark_shown(item)
    ctx = _exercise_context(item)
    ctx.update({"session": s, "total": s.total(), "number": item.position, "error": error,
                "posted": request.POST if error else None,
                "progress_pct": round(100 * (item.position - 1) / max(1, s.total()))})
    return render(request, "learning/session_play.html", ctx)


def session_feedback(request, pk, pos):
    s = get_object_or_404(StudySession, pk=pk)
    item = get_object_or_404(SessionItem.objects.select_related("exercise", "attempt"), session=s, position=pos)
    if item.attempt is None:
        return redirect(s)
    if s.is_assessment and s.status != StudySession.Status.FINISHED:
        raise Http404("No modo avaliação as correções aparecem só no final.")
    nxt = s.next_item()
    ctx = _exercise_context(item)
    attempt = item.attempt
    ctx.update({"session": s, "attempt": attempt, "total": s.total(), "number": item.position,
                "written": getattr(attempt, "written", None) if attempt.result == "pending" else None,
                "next_item": nxt, "review_item": ReviewItem.objects.filter(exercise=item.exercise).first(),
                "progress_pct": round(100 * item.position / max(1, s.total()))})
    return render(request, "learning/session_feedback.html", ctx)


@require_POST
def session_pause(request, pk):
    s = get_object_or_404(StudySession, pk=pk)
    sessions.pause(s)
    messages.success(request, "Sessão interrompida. Você pode retomá-la quando quiser pelo painel.")
    return redirect("learning:dashboard")


@require_POST
def session_finish(request, pk):
    s = get_object_or_404(StudySession, pk=pk)
    sessions.finish(s)
    return redirect("learning:session_result", pk=pk)


def session_result(request, pk):
    s = get_object_or_404(StudySession.objects.select_related("chapter", "passage"), pk=pk)
    if s.status != StudySession.Status.FINISHED and s.next_item() is None:
        sessions.finish(s)
    items = list(s.items.select_related("exercise", "exercise__passage", "attempt", "attempt__written")
                 .order_by("position"))
    answered = [i for i in items if i.attempt]
    scores = [i.attempt.effective_score for i in answered if i.attempt.effective_score is not None]
    pending = [i for i in answered if i.attempt.effective_score is None]
    wrong = [i for i in answered if i.attempt.effective_score is not None and i.attempt.effective_score < 0.99]
    ctx = {
        "session": s, "items": items, "answered": len(answered), "total": len(items),
        "score_pct": round(100 * sum(scores) / len(scores)) if scores else None,
        "correct_count": sum(1 for x in scores if x >= 0.99), "wrong_count": len(wrong), "pending": pending,
        "passed": (s.result_score or 0) >= sessions.PASS_SCORE if s.kind == StudySession.Kind.CHAPTER_ASSESSMENT else None,
        "unfinished": s.status != StudySession.Status.FINISHED,
        "minutes": round(sum(i.attempt.duration_seconds for i in answered) / 60, 1),
    }
    passages = {i.exercise.passage for i in items if i.exercise.passage_id}
    ctx["passages"] = sorted(passages, key=lambda p: p.position)
    return render(request, "learning/session_result.html", ctx)


def session_history(request):
    qs = StudySession.objects.select_related("chapter").order_by("-last_activity_at")
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    return render(request, "learning/session_history.html", {"page": page})


# ---------------------------------------------------------------------------
# Marcar e sinalizar
# ---------------------------------------------------------------------------

@require_POST
def mark_for_review(request, code):
    ex = get_object_or_404(Exercise, code=code)
    review.flag(ex)
    messages.success(request, "Questão marcada para revisão: ela aparecerá na fila de revisões pendentes.")
    return redirect(_safe_next(request, "learning:review_queue"))


@require_http_methods(["GET", "POST"])
def flag_issue(request, code):
    ex = get_object_or_404(Exercise, code=code)
    form = IssueForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        issue = form.save(commit=False)
        issue.exercise = ex
        issue.exercise_version = ex.version
        issue.user_answer = request.POST.get("user_answer", "")[:1000]
        issue.save()
        messages.success(request, "Obrigado! O problema foi registrado no painel editorial.")
        return redirect(_safe_next(request, "learning:dashboard"))
    return render(request, "learning/flag_issue.html", {"form": form, "ex": ex,
                                                        "next": request.GET.get("next", ""),
                                                        "user_answer": request.GET.get("resposta", "")})


def _safe_next(request, default):
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and nxt.startswith("/") and not nxt.startswith("//"):
        return nxt
    return reverse(default)


# ---------------------------------------------------------------------------
# Revisão espaçada e caderno de erros
# ---------------------------------------------------------------------------

def review_queue(request):
    now = timezone.now()
    comp = mastery.competency_scores()
    due = sorted(review.due_queryset(now).select_related("exercise__chapter", "exercise__competency"),
                 key=lambda i: review.priority(i, comp, now), reverse=True)
    upcoming = (ReviewItem.objects.filter(due_at__gt=now, exercise__is_active=True)
                .select_related("exercise__chapter").order_by("due_at")[:15])
    by_stage = {i: ReviewItem.objects.filter(stage=i).count() for i in range(5)}
    return render(request, "learning/review_queue.html", {
        "due": due, "upcoming": upcoming, "by_stage": by_stage, "intervals": review.INTERVALS})


def notebook(request):
    qs = (ReviewItem.objects.filter(error_count__gt=0)
          .select_related("exercise", "exercise__chapter", "exercise__competency")
          .prefetch_related("exercise__grammar_topics", "exercise__vocabulary_topics"))
    f_state = request.GET.get("estado", "")
    f_chapter = request.GET.get("capitulo", "")
    f_comp = request.GET.get("competencia", "")
    if f_state in ReviewItem.Recovery.values:
        qs = qs.filter(recovery=f_state)
    if f_chapter:
        qs = qs.filter(exercise__chapter__code=f_chapter)
    if f_comp:
        qs = qs.filter(exercise__competency__code=f_comp)
    order = request.GET.get("ordem", "erros")
    qs = qs.order_by({"erros": "-error_count", "recentes": "-last_attempt_at", "revisao": "due_at"}.get(order, "-error_count"))
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    rows = []
    for item in page:
        last_wrong = (Attempt.objects.filter(exercise=item.exercise).exclude(result="correct")
                      .order_by("-created_at").first())
        rows.append({"item": item, "ex": item.exercise, "last_wrong": last_wrong})
    counts = {state: ReviewItem.objects.filter(error_count__gt=0, recovery=state).count()
              for state in ReviewItem.Recovery.values}
    return render(request, "learning/notebook.html", {
        "page": page, "rows": rows, "states": ReviewItem.Recovery.choices, "counts": counts,
        "chapters": Chapter.objects.filter(is_active=True, is_planned=False), "competencies": Competency.objects.all(),
        "f_state": f_state, "f_chapter": f_chapter, "f_comp": f_comp, "order": order,
        "query": request.GET.urlencode()})


# ---------------------------------------------------------------------------
# Produção escrita
# ---------------------------------------------------------------------------

def written_list(request):
    qs = WrittenAnswer.objects.select_related("attempt", "attempt__exercise", "attempt__exercise__chapter")
    flt = request.GET.get("filtro", "")
    if flt == "pendentes":
        qs = qs.filter(assessed_score__isnull=True)
    elif flt == "revisar":
        qs = qs.filter(marked_for_review=True)
    page = Paginator(qs, 15).get_page(request.GET.get("page"))
    return render(request, "learning/written_list.html", {"page": page, "flt": flt})


@require_http_methods(["GET", "POST"])
def written_assess(request, pk):
    written = get_object_or_404(WrittenAnswer.objects.select_related("attempt", "attempt__exercise"), pk=pk)
    ex = written.attempt.exercise
    if request.method == "POST":
        checked = []
        for v in request.POST.getlist("criteria"):
            try:
                checked.append(int(v))
            except ValueError:
                continue
        overall = request.POST.get("overall") or None
        if overall not in (None, "correct", "partial", "incorrect"):
            overall = None
        by = "manual" if request.POST.get("by") == "manual" else "self"
        written.notes = request.POST.get("notes", "")[:2000]
        sessions.self_assess(written, checked, request.POST.get("marked_for_review") == "1", overall, by)
        messages.success(request, "Avaliação registrada.")
        nxt = request.POST.get("next")
        if nxt and nxt.startswith("/") and not nxt.startswith("//"):
            return redirect(nxt)
        return redirect("learning:written_list")
    return render(request, "learning/written_assess.html", {"written": written, "ex": ex,
                                                             "criteria": list(enumerate(ex.criteria_list()))})


# ---------------------------------------------------------------------------
# Progresso e configurações
# ---------------------------------------------------------------------------

def progress(request):
    if not Mastery.objects.exists() and Attempt.objects.exists():
        mastery.refresh_all()
    groups = []
    for scope, label in [(Mastery.Scope.CHAPTER, "Capítulos"), (Mastery.Scope.COMPETENCY, "Competências"),
                         (Mastery.Scope.GRAMMAR, "Gramática"), (Mastery.Scope.VOCABULARY, "Vocabulário"),
                         (Mastery.Scope.OBJECTIVE, "Objetivos")]:
        rows = list(Mastery.objects.filter(scope=scope).order_by("-score"))
        groups.append({"label": label, "rows": rows})
    return render(request, "learning/progress.html", {
        "overall": Mastery.objects.filter(scope=Mastery.Scope.OVERALL).first(), "groups": groups,
        "constants": {"cap": round(mastery.CAP_WITHOUT_RETENTION * 100), "evidence": mastery.EVIDENCE_TARGET}})


@require_http_methods(["GET", "POST"])
def settings_view(request):
    setting = UserSetting.get()
    form = SettingsForm(request.POST or None, instance=setting)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Preferências salvas.")
        return redirect("learning:settings")
    return render(request, "learning/settings.html", {"form": form})


def attempt_history(request):
    qs = Attempt.objects.select_related("exercise", "exercise__chapter")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(exercise__code__icontains=q) | Q(answer_display__icontains=q))
    page = Paginator(qs, 30).get_page(request.GET.get("page"))
    return render(request, "learning/attempt_history.html", {"page": page, "q": q})

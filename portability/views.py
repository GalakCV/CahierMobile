"""Dados (exportação, importação, backup/restauração) e painel editorial."""
from __future__ import annotations

import json
import secrets
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.models import LogEntry
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from content.models import Chapter, ContentIssue, ExerciseVersion
from content.quality import report as quality_report

from learning import sync

from . import backup, exporter, importer
from .models import ImportLog

PENDING_DIR_NAME = "imports-pendentes"


def _json_download(data: dict, filename: str) -> HttpResponse:
    body = json.dumps(data, ensure_ascii=False, indent=2)
    resp = HttpResponse(body, content_type="application/json; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


def data_home(request):
    return render(request, "portability/data_home.html", {
        "chapters": Chapter.objects.filter(is_active=True).order_by("number"),
        "backups": backup.list_backups()[:20], "backup_dir": settings.BACKUP_DIR,
        "imports": ImportLog.objects.all()[:10], "confirm_phrase": backup.CONFIRM_PHRASE,
        "max_import_mb": settings.MAX_IMPORT_BYTES // (1024 * 1024),
        "max_restore_mb": settings.MAX_RESTORE_BYTES // (1024 * 1024),
        "mobile_url": settings.CAHIER_MOBILE_URL})


def export_view(request, kind):
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
    if kind == "conteudo":
        code = request.GET.get("capitulo")
        if code:
            ch = Chapter.objects.filter(code=code).first()
            if ch is None:
                raise Http404("Capítulo não encontrado.")
            return _json_download(exporter.export_content(ch), f"cahier-conteudo-{ch.code}-{stamp}.json")
        return _json_download(exporter.export_content(), f"cahier-conteudo-{stamp}.json")
    if kind == "progresso":
        return _json_download(exporter.export_progress(), f"cahier-progresso-{stamp}.json")
    if kind == "caderno":
        return _json_download(exporter.export_error_notebook(), f"cahier-caderno-de-erros-{stamp}.json")
    if kind == "completo":
        return _json_download(exporter.export_full(), f"cahier-completo-{stamp}.json")
    raise Http404("Exportação desconhecida.")


def _pending_dir() -> Path:
    path = Path(settings.DATA_DIR) / PENDING_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


@require_http_methods(["GET", "POST"])
def import_view(request):
    ctx = {"max_mb": settings.MAX_IMPORT_BYTES // (1024 * 1024)}
    if request.method == "POST" and request.POST.get("token"):
        token = request.POST["token"]
        if not token.isalnum():
            raise Http404()
        path = _pending_dir() / f"{token}.json"
        if not path.exists():
            messages.error(request, "A simulação expirou. Envie o arquivo novamente.")
            return redirect("dados:import")
        data = json.loads(path.read_text(encoding="utf-8"))
        update = request.POST.get("existing") == "update"
        skip = request.POST.get("existing") == "skip"
        rep = importer.run_import(data, update_existing=update, skip_existing=skip)
        filename = request.POST.get("filename", "arquivo.json")[:200]
        ImportLog.objects.create(filename=filename, update_existing=update, report=rep.as_dict(),
                                 status=ImportLog.Status.APPLIED if rep.applied else ImportLog.Status.FAILED)
        path.unlink(missing_ok=True)
        if rep.applied:
            from learning.mastery import refresh_all
            refresh_all()
            messages.success(request, "Importação concluída.")
        else:
            messages.error(request, "A importação foi recusada e nada foi alterado.")
        ctx.update({"report": rep, "filename": filename, "final": True})
        return render(request, "portability/import.html", ctx)

    if request.method == "POST":
        upload = request.FILES.get("file")
        existing = request.POST.get("existing", "refuse")
        update, skip = existing == "update", existing == "skip"
        if upload is None:
            ctx["error"] = "Selecione um arquivo .json."
        elif not upload.name.lower().endswith(".json"):
            ctx["error"] = "O arquivo precisa ter extensão .json."
        elif upload.size > settings.MAX_IMPORT_BYTES:
            ctx["error"] = f"Arquivo maior que o limite de {ctx['max_mb']} MB."
        else:
            try:
                data = importer.load_json_bytes(upload.read())
            except ValueError as exc:
                ctx["error"] = str(exc)
            else:
                rep = importer.run_import(data, update_existing=update, skip_existing=skip, dry_run=True)
                ImportLog.objects.create(filename=upload.name[:200], update_existing=update, report=rep.as_dict(),
                                         status=ImportLog.Status.DRY_RUN if rep.ok else ImportLog.Status.FAILED)
                ctx.update({"report": rep, "filename": upload.name, "existing": existing})
                if rep.ok:
                    token = secrets.token_hex(16)
                    (_pending_dir() / f"{token}.json").write_text(json.dumps(data, ensure_ascii=False),
                                                                  encoding="utf-8")
                    ctx["token"] = token
    return render(request, "portability/import.html", ctx)


@require_POST
def backup_create(request):
    try:
        path = backup.create_backup(request.POST.get("label") or "manual")
    except backup.BackupError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Backup criado: {path.name}")
    return redirect("dados:home")


def backup_download(request, name):
    try:
        path = backup.resolve_backup(name)
    except backup.BackupError as exc:
        raise Http404(str(exc))
    return FileResponse(open(path, "rb"), as_attachment=True, filename=path.name)


@require_http_methods(["GET", "POST"])
def backup_restore(request):
    ctx = {"backups": backup.list_backups(), "confirm_phrase": backup.CONFIRM_PHRASE,
           "selected": request.GET.get("nome", ""),
           "max_mb": settings.MAX_RESTORE_BYTES // (1024 * 1024)}
    if request.method == "POST":
        upload = request.FILES.get("file")
        name = request.POST.get("name", "")
        temp = None
        try:
            if upload:
                if upload.size > settings.MAX_RESTORE_BYTES:
                    raise backup.BackupError(f"Arquivo maior que o limite de {ctx['max_mb']} MB.")
                temp = Path(settings.DATA_DIR) / f"upload-restauracao-{secrets.token_hex(6)}.sqlite3"
                with open(temp, "wb") as fh:
                    for chunk in upload.chunks():
                        fh.write(chunk)
                path = temp
            elif name:
                path = backup.resolve_backup(name)
            else:
                raise backup.BackupError("Escolha um backup da lista ou envie um arquivo.")
            summary = backup.restore_backup(path, request.POST.get("confirmation", ""))
        except backup.BackupError as exc:
            ctx["error"] = str(exc)
            ctx["selected"] = name
            return render(request, "portability/restore.html", ctx, status=400)
        finally:
            if temp:
                temp.unlink(missing_ok=True)
        messages.success(request, (f"Backup restaurado ({summary['exercises']} questões, {summary['attempts']} "
                                   f"tentativas). Um backup de segurança foi criado antes: {summary['safety_backup']}."))
        return redirect("learning:dashboard")
    return render(request, "portability/restore.html", ctx)


def editorial(request):
    rep = quality_report()
    return render(request, "portability/editorial.html", {
        "issues": ContentIssue.objects.filter(status=ContentIssue.Status.OPEN).select_related("exercise")[:50],
        "issue_count": ContentIssue.objects.filter(status=ContentIssue.Status.OPEN).count(),
        "report": rep,
        "log": LogEntry.objects.select_related("content_type", "user").order_by("-action_time")[:20],
        "versions": ExerciseVersion.objects.select_related("exercise").order_by("-created_at")[:20],
        "imports": ImportLog.objects.all()[:10],
    })


def sync_export(request):
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
    return _json_download(sync.export_sync(), f"cahier-sync-computador-{stamp}.json")


@require_POST
def sync_import(request):
    upload = request.FILES.get("file")
    if upload is None:
        messages.error(request, "Selecione o arquivo de sincronização (.json) gerado no celular.")
        return redirect("dados:home")
    if upload.size > settings.MAX_RESTORE_BYTES:
        messages.error(request, "Arquivo grande demais.")
        return redirect("dados:home")
    try:
        data = importer.load_json_bytes(upload.read())
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("dados:home")
    try:
        backup.create_backup("antes-da-sincronizacao")
    except backup.BackupError:
        pass
    rep = sync.import_sync(data)
    if not rep.ok:
        messages.error(request, "Sincronização recusada: " + " ".join(rep.errors[:5]))
    elif rep.total_added() or rep.updated_written:
        parts = [f"{v} {k}" for k, v in rep.added.items() if v]
        if rep.updated_written:
            parts.append(f"{rep.updated_written} autoavaliação(ões) atualizada(s)")
        messages.success(request, "Progresso do celular importado: " + ", ".join(parts) +
                         ". A fila de revisão e o domínio foram recalculados.")
    else:
        messages.info(request, "Nada novo: este computador já tinha todo o progresso do arquivo.")
    for s in rep.skipped:
        messages.warning(request, s)
    return redirect("dados:home")

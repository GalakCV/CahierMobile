"""
Backup e restauração do banco SQLite.

- O backup usa a API de backup do SQLite (cópia consistente mesmo com o
  servidor rodando) e grava em ``data/backups/cahier-AAAAMMDD-HHMMSS-rotulo.sqlite3``.
- Cada backup é verificado com ``PRAGMA integrity_check``.
- A restauração exige a frase de confirmação ``RESTAURAR``, valida o arquivo
  (cabeçalho SQLite, integridade e tabelas esperadas) e sempre cria antes um
  backup de segurança do estado atual. Depois aplica as migrations pendentes.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.db import connection

CONFIRM_PHRASE = "RESTAURAR"
SQLITE_HEADER = b"SQLite format 3\x00"
REQUIRED_TABLES = {"django_migrations", "content_exercise", "content_chapter", "learning_attempt"}
NAME_RE = re.compile(r"^cahier-\d{8}-\d{6}(-[a-z0-9-]{1,40})?\.sqlite3$")


class BackupError(Exception):
    pass


@dataclass
class BackupInfo:
    name: str
    path: Path
    size: int
    created: datetime

    @property
    def size_kb(self) -> int:
        return max(1, round(self.size / 1024))


def backup_dir() -> Path:
    path = Path(settings.BACKUP_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _slug(label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return s[:40] or "manual"


def create_backup(label: str = "manual", directory: Path | None = None) -> Path:
    directory = directory or backup_dir()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = directory / f"cahier-{stamp}-{_slug(label)}.sqlite3"
    n = 1
    while target.exists():
        n += 1
        target = directory / f"cahier-{stamp}-{_slug(label)}-{n}.sqlite3"
    connection.ensure_connection()
    dest = sqlite3.connect(target)
    try:
        connection.connection.backup(dest)
        ok = dest.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        dest.close()
    if ok != "ok":
        target.unlink(missing_ok=True)
        raise BackupError(f"O backup gerado não passou na verificação de integridade: {ok}")
    return target


def list_backups() -> list[BackupInfo]:
    out = []
    for p in backup_dir().glob("cahier-*.sqlite3"):
        if NAME_RE.match(p.name):
            st = p.stat()
            out.append(BackupInfo(p.name, p, st.st_size, datetime.fromtimestamp(st.st_mtime)))
    return sorted(out, key=lambda b: b.name, reverse=True)


def resolve_backup(name: str) -> Path:
    """Aceita apenas nomes de backup válidos dentro da pasta de backups (evita path traversal)."""
    if not NAME_RE.match(name or ""):
        raise BackupError("Nome de backup inválido.")
    path = backup_dir() / name
    if not path.is_file():
        raise BackupError("Backup não encontrado.")
    return path


def inspect(path: Path) -> dict:
    """Valida um arquivo de backup e devolve um resumo do conteúdo."""
    path = Path(path)
    with open(path, "rb") as fh:
        if fh.read(16) != SQLITE_HEADER:
            raise BackupError("O arquivo não é um banco SQLite.")
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise BackupError(f"Não foi possível abrir o arquivo: {exc}")
    try:
        status = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if status != "ok":
            raise BackupError(f"Arquivo corrompido: {status}")
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = REQUIRED_TABLES - tables
        if missing:
            raise BackupError("O arquivo não parece ser um backup do Cahier (faltam tabelas: "
                              + ", ".join(sorted(missing)) + ").")
        count = lambda t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: E731
        return {"exercises": count("content_exercise"), "chapters": count("content_chapter"),
                "attempts": count("learning_attempt")}
    except sqlite3.Error as exc:
        raise BackupError(f"Arquivo inválido: {exc}")
    finally:
        conn.close()


def restore_backup(path: Path, confirmation: str) -> dict:
    if (confirmation or "").strip() != CONFIRM_PHRASE:
        raise BackupError(f"Para restaurar, digite exatamente {CONFIRM_PHRASE}.")
    summary = inspect(path)
    safety = create_backup("antes-da-restauracao")
    src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        connection.ensure_connection()
        if connection.in_atomic_block:
            raise BackupError("Restauração não pode ocorrer dentro de uma transação.")
        src.backup(connection.connection)
    finally:
        src.close()
    connection.close()
    call_command("migrate", interactive=False, verbosity=0)
    summary["safety_backup"] = safety.name
    return summary

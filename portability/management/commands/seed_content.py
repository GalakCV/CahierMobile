"""Carrega o conteúdo inicial (data/seed/*.json). Seguro para rodar mais de uma vez."""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from portability.importer import run_import

SEED_DIR = Path(settings.BASE_DIR) / "seed"


class Command(BaseCommand):
    help = "Carrega o conteúdo inicial. Use --update para atualizar o conteúdo já carregado (o histórico é mantido)."

    def add_arguments(self, parser):
        parser.add_argument("--update", action="store_true", help="Atualiza itens existentes com a versão dos arquivos.")

    def handle(self, *args, **opts):
        files = sorted(SEED_DIR.glob("*.json"))
        if not files:
            raise CommandError(f"Nenhum arquivo em {SEED_DIR}")
        from content.models import Exercise
        if Exercise.objects.exists() and not opts["update"]:
            self.stdout.write("O conteúdo inicial já está carregado. Use --update para atualizá-lo.")
            return
        for path in files:
            data = json.loads(path.read_text(encoding="utf-8"))
            rep = run_import(data, update_existing=opts["update"])
            if not rep.ok:
                for e in rep.errors[:30]:
                    self.stderr.write(f"  {e}")
                raise CommandError(f"Falha ao importar {path.name}; nada deste arquivo foi gravado.")
            summary = ", ".join(f"{v} {k}" for k, v in {**rep.created, **rep.updated}.items())
            self.stdout.write(self.style.SUCCESS(f"{path.name}: {summary or 'sem alterações'}"))
        from learning.mastery import refresh_all
        refresh_all()

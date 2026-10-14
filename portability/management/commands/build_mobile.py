"""Gera o app móvel (PWA) com o conteúdo atual do banco em mobile/dist/ (ou --out)."""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from portability.mobile import build


class Command(BaseCommand):
    help = "Gera o app para celular (PWA offline) a partir do conteúdo do banco."

    def add_arguments(self, parser):
        parser.add_argument("--out", default=str(Path(settings.BASE_DIR) / "mobile" / "dist"))

    def handle(self, *args, out, **opts):
        info = build(Path(out))
        self.stdout.write(self.style.SUCCESS(
            f"App móvel gerado em {info['dest']}: {info['exercises']} questões, conteúdo {info['content_kb']} KB, "
            f"{info['files']} arquivos, versão {info['cache_version']}."))

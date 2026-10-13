import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from content.models import Chapter
from portability import exporter


class Command(BaseCommand):
    help = "Exporta conteúdo, progresso, caderno de erros ou tudo para JSON."

    def add_arguments(self, parser):
        parser.add_argument("output")
        parser.add_argument("--kind", choices=["conteudo", "progresso", "caderno", "completo"], default="conteudo")
        parser.add_argument("--chapter", help="Código do capítulo (apenas para --kind conteudo)")

    def handle(self, *args, output, kind, chapter, **opts):
        if kind == "conteudo":
            ch = None
            if chapter:
                ch = Chapter.objects.filter(code=chapter).first()
                if ch is None:
                    raise CommandError(f"Capítulo inexistente: {chapter}")
            data = exporter.export_content(ch)
        else:
            data = {"progresso": exporter.export_progress, "caderno": exporter.export_error_notebook,
                    "completo": exporter.export_full}[kind]()
        Path(output).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Exportado para {output}"))

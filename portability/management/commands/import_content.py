import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from portability.importer import load_json_bytes, run_import


class Command(BaseCommand):
    help = "Importa um pacote de conteúdo JSON (tudo ou nada)."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--update", action="store_true", help="Atualiza itens com o mesmo código.")
        parser.add_argument("--dry-run", action="store_true", help="Apenas valida e simula, sem gravar.")

    def handle(self, *args, path, update, dry_run, **opts):
        try:
            data = load_json_bytes(Path(path).read_bytes())
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc))
        rep = run_import(data, update_existing=update, dry_run=dry_run)
        self.stdout.write(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
        if not rep.ok:
            raise CommandError("Importação recusada; nada foi gravado.")

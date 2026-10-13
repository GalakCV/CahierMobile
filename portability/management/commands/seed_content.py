"""Carrega o conteúdo inicial (seed/*.json).

Por padrão é incremental: o que já existe fica como está (inclusive edições feitas no
painel) e só os itens novos são acrescentados. Assim, ao atualizar o Cahier, basta
rodar este comando de novo para receber questões e textos novos sem perder nada.
Use --update para sobrescrever o conteúdo existente com a versão dos arquivos
(as questões alteradas ganham nova versão; o histórico é preservado).
"""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from portability.importer import run_import

SEED_DIR = Path(settings.BASE_DIR) / "seed"


class Command(BaseCommand):
    help = "Carrega o conteúdo inicial, acrescentando só o que é novo (ou atualizando tudo com --update)."

    def add_arguments(self, parser):
        parser.add_argument("--update", action="store_true",
                            help="Sobrescreve itens existentes com a versão dos arquivos.")

    def handle(self, *args, **opts):
        files = sorted(SEED_DIR.glob("*.json"))
        if not files:
            raise CommandError(f"Nenhum arquivo em {SEED_DIR}")
        total_new = 0
        for path in files:
            data = json.loads(path.read_text(encoding="utf-8"))
            rep = run_import(data, update_existing=opts["update"], skip_existing=not opts["update"])
            if not rep.ok:
                for e in rep.errors[:30]:
                    self.stderr.write(f"  {e}")
                raise CommandError(f"Falha ao importar {path.name}; nada deste arquivo foi gravado.")
            changed = {**rep.created, **({k: v for k, v in rep.updated.items()} if opts["update"] else {})}
            total_new += sum(rep.created.values())
            summary = ", ".join(f"{v} {k}" for k, v in changed.items())
            self.stdout.write(self.style.SUCCESS(f"{path.name}: {summary or 'nada novo'}"))
        if not opts["update"] and total_new == 0:
            self.stdout.write("O conteúdo inicial já estava completo.")
        from learning.mastery import refresh_all
        refresh_all()

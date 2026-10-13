from django.core.management.base import BaseCommand, CommandError

from content.quality import report


class Command(BaseCommand):
    help = "Verifica a consistência do conteúdo cadastrado."

    def add_arguments(self, parser):
        parser.add_argument("--warnings", action="store_true", help="Lista também os avisos.")

    def handle(self, *args, **opts):
        rep = report()
        for c in rep["chapters"]:
            status = "; ".join(c["problems"]) or "completo"
            self.stdout.write(f"{c['chapter']}: {status} ({len(c['types'])} tipos de exercício)")
        for r in rep["rows"]:
            if r["errors"] or opts["warnings"]:
                self.stdout.write(f"  {r['exercise'].code}: {'; '.join(r['errors'] + (r['warnings'] if opts['warnings'] else []))}")
        if rep["missing_types"]:
            self.stdout.write("Tipos sem questões: " + ", ".join(rep["missing_types"]))
        t = rep["totals"]
        self.stdout.write(f"{t.get('exercises', 0)} questões, {t.get('errors', 0)} erros, {t.get('warnings', 0)} avisos")
        if t.get("errors"):
            raise CommandError("O conteúdo tem erros.")

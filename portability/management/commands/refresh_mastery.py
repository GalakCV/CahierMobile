from django.core.management.base import BaseCommand

from learning.mastery import refresh_all


class Command(BaseCommand):
    help = "Recalcula todos os indicadores de domínio."

    def handle(self, *args, **opts):
        refresh_all()
        self.stdout.write(self.style.SUCCESS("Domínio recalculado."))

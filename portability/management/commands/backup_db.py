from django.core.management.base import BaseCommand, CommandError

from portability.backup import BackupError, create_backup


class Command(BaseCommand):
    help = "Cria um backup datado do banco SQLite em data/backups/."

    def add_arguments(self, parser):
        parser.add_argument("--label", default="manual")

    def handle(self, *args, label, **opts):
        try:
            path = create_backup(label)
        except BackupError as exc:
            raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS(f"Backup criado: {path}"))

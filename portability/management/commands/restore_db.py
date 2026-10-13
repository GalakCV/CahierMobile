from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from portability.backup import CONFIRM_PHRASE, BackupError, restore_backup


class Command(BaseCommand):
    help = f"Restaura um backup. Exige --confirm {CONFIRM_PHRASE}. Um backup de segurança é criado antes."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--confirm", default="")

    def handle(self, *args, path, confirm, **opts):
        try:
            summary = restore_backup(Path(path), confirm)
        except BackupError as exc:
            raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS(f"Restaurado. Backup de segurança: {summary['safety_backup']}"))

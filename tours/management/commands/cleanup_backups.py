from django.core.management.base import BaseCommand
from django.conf import settings
import os

class Command(BaseCommand):
    help = 'Cleanup old database backups, keeping only the 3 most recent'

    def handle(self, *args, **options):
        backup_dir = settings.DBBACKUP_STORAGE_OPTIONS['location']
        backups = []
        for file in os.listdir(backup_dir):
            if file.endswith('.psql'):
                backups.append(os.path.join(backup_dir, file))

        # Sort backups by modification time (newest first)
        backups.sort(key=os.path.getmtime, reverse=True)

        # Remove all but the 3 most recent backups
        for backup in backups[3:]:
            try:
                os.remove(backup)
                self.stdout.write(self.style.SUCCESS(f'Deleted old backup: {backup}'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Failed to delete {backup}: {str(e)}'))

        self.stdout.write(self.style.SUCCESS('Backup cleanup completed'))

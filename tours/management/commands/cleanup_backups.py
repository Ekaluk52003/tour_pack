import os
from django.core.management.base import BaseCommand
from django.conf import settings

class Command(BaseCommand):
    help = 'Cleanup old database backups, keeping only the most recent ones'

    def handle(self, *args, **options):
        backup_dir = settings.DBBACKUP_STORAGE_OPTIONS['location']
        self.stdout.write(f"Checking for backups in: {backup_dir}")

        backups = []
        for file in os.listdir(backup_dir):
            self.stdout.write(f"Found file: {file}")
            if file.endswith('.psql'):  # Specifically looking for .psql files
                full_path = os.path.join(backup_dir, file)
                backups.append((full_path, os.path.getmtime(full_path)))

        self.stdout.write(f"Total .psql backup files found: {len(backups)}")

        # Sort backups by modification time (newest first)
        backups.sort(key=lambda x: x[1], reverse=True)

        # Keep the most recent backups
        to_keep = backups[:settings.DBBACKUP_CLEANUP_KEEP]
        to_delete = backups[settings.DBBACKUP_CLEANUP_KEEP:]

        for backup_path, _ in to_delete:
            try:
                os.remove(backup_path)
                self.stdout.write(self.style.SUCCESS(f'Deleted old backup: {backup_path}'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Failed to delete {backup_path}: {str(e)}'))

        self.stdout.write(self.style.SUCCESS(f'Backup cleanup completed. Kept {len(to_keep)} backups, deleted {len(to_delete)} backups.'))
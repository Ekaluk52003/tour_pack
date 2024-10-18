from django.contrib import admin
from django.urls import path
from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.management import call_command
from django.conf import settings
import os
from io import StringIO
from .models import BackupManagement
from django.db import connection
from django.http import FileResponse, Http404
from django.views.decorators.csrf import csrf_protect
from django.utils.decorators import method_decorator
from django.core.files.storage import FileSystemStorage

@admin.register(BackupManagement)
class BackupManagementAdmin(admin.ModelAdmin):
    change_list_template = 'admin/backup_changelist.html'

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['backups'] = self.get_backups()
        return super().changelist_view(request, extra_context=extra_context)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('create_backup/', self.admin_site.admin_view(self.create_backup_view),
                 name='backup_manager_backupmanagement_create_backup'),
            path('restore_db/<str:filename>/',
                 self.admin_site.admin_view(self.restore_db_view),
                 name='backup_manager_backupmanagement_restore_db'),
            path('confirm_restore_db/<str:filename>/',
                 self.admin_site.admin_view(self.confirm_restore_db_view),
                 name='backup_manager_backupmanagement_confirm_restore_db'),

            path('download_backup/<str:filename>/',
                 self.admin_site.admin_view(self.download_backup_view),
                 name='backup_manager_backupmanagement_download_backup'),
            path('upload_backup/',
                 self.admin_site.admin_view(self.upload_backup_view),
                 name='backup_manager_backupmanagement_upload_backup'),
        ]
        return custom_urls + urls

    def get_backups(self):
        backup_dir = settings.DBBACKUP_STORAGE_OPTIONS['location']
        backups = []
        if os.path.exists(backup_dir):
            for file in os.listdir(backup_dir):
                if file.endswith('.psql'):
                    backups.append(file)
        return sorted(backups, reverse=True)

    def download_backup_view(self, request, filename):
        backup_dir = settings.DBBACKUP_STORAGE_OPTIONS['location']
        file_path = os.path.join(backup_dir, filename)

        if os.path.exists(file_path):
            response = FileResponse(open(file_path, 'rb'))
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
        else:
            raise Http404("Backup file not found")

    @method_decorator(csrf_protect)
    def upload_backup_view(self, request):
        if request.method == 'POST' and request.FILES.get('backup_file'):
            uploaded_file = request.FILES['backup_file']
            if not uploaded_file.name.endswith('.psql'):
                messages.error(request, "Only .psql files are allowed.")
                return redirect('..')

            backup_dir = settings.DBBACKUP_STORAGE_OPTIONS['location']

            os.makedirs(backup_dir, exist_ok=True)

            fs = FileSystemStorage(location=backup_dir)

            filename = fs.save(uploaded_file.name, uploaded_file)

            messages.success(request, f"Backup file '{uploaded_file.name}' uploaded successfully.")
            return redirect('..')
        
        return render(request, 'admin/upload_backup.html')

    def create_backup_view(self, request):
        backup_dir = settings.DBBACKUP_STORAGE_OPTIONS['location']
        os.makedirs(backup_dir, exist_ok=True)
        initial_files = set(os.listdir(backup_dir))

        try:
            output = StringIO()
            call_command('dbbackup', '--clean', '--noinput', stdout=output, stderr=output)
            output_str = output.getvalue()

            new_files = set(os.listdir(backup_dir))
            created_files = new_files - initial_files

            if created_files:
                messages.success(request, f'Database backup created successfully. New files: {", ".join(created_files)}')
            else:
                messages.warning(request, f'Backup command executed, but no new backup file was found. Output: {output_str}')
        except Exception as e:
            messages.error(request, f'Error creating backup: {str(e)}')
        return redirect('..')

    def restore_db_view(self, request, filename):
        backup_file = os.path.join(settings.DBBACKUP_STORAGE_OPTIONS['location'], filename)

        if not os.path.exists(backup_file):
            messages.error(request, f"Backup file {filename} not found.")
            return redirect('..')

        if os.path.getsize(backup_file) == 0:
            messages.error(request, f"Backup file {filename} is empty.")
            return redirect('..')

        try:
            with open(backup_file, 'r') as f:
                first_line = f.readline().strip()
                if not first_line.startswith('--'):
                    messages.error(request, f"Backup file {filename} does not appear to be a valid PostgreSQL dump.")
                    return redirect('..')

            return render(request, 'admin/restore_db_confirm.html', {'filename': filename})
        except Exception as e:
            messages.error(request, f'Error checking backup file: {str(e)}')
            return redirect('..')

    def confirm_restore_db_view(self, request, filename):
        if request.method != 'POST':
            return redirect('..')

        backup_file = os.path.join(settings.DBBACKUP_STORAGE_OPTIONS['location'], filename)

        try:
            output = StringIO()
            call_command('dbrestore', '--noinput', '--input-filename', filename, stdout=output, stderr=output)
            output_str = output.getvalue()

            # Verify database state
            if self.verify_database_state():
                messages.success(request, f'Database restored successfully from {filename}. Database contains tables.')
            else:
                messages.warning(request, f'Restore command executed, but the database appears to be empty. Please verify the database state.')

        except CommandError as e:
            messages.error(request, f'Error restoring database: {str(e)}')
        except Exception as e:
            messages.error(request, f'Unexpected error during database restore: {str(e)}')

        return redirect('admin:backup_manager_backupmanagement_changelist')

    def verify_database_state(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'")
            table_count = cursor.fetchone()[0]
        return table_count > 0

from django.urls import path
from django.contrib import admin
from .admin import BackupManagementAdmin
from .models import BackupManagement  # Import the model

app_name = 'backup_manager'

urlpatterns = [
    # If you need any app-specific views, you can add them here
]

# Add the admin URLs
backup_management_admin = BackupManagementAdmin(BackupManagement, admin.site)
urlpatterns += [
    path('admin/backup_manager/backupmanagement/', admin.site.admin_view(backup_management_admin.changelist_view), name='backup_manager_backupmanagement_changelist'),
    path('admin/backup_manager/backupmanagement/create_backup/', admin.site.admin_view(backup_management_admin.create_backup_view), name='backup_manager_backupmanagement_create_backup'),
    path('admin/backup_manager/backupmanagement/restore_db/<str:filename>/', admin.site.admin_view(backup_management_admin.restore_db_view), name='backup_manager_backupmanagement_restore_db'),
    path('admin/backup_manager/backupmanagement/confirm_restore_db/<str:filename>/', admin.site.admin_view(backup_management_admin.confirm_restore_db_view), name='backup_manager_backupmanagement_confirm_restore_db'),
]
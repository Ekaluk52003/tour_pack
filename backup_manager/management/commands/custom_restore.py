import os
import subprocess
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import connections


class Command(BaseCommand):
    help = 'Restore database from backup file with role filtering'

    def add_arguments(self, parser):
        parser.add_argument('--filename', required=True, help='Backup file name to restore from')

    def handle(self, *args, **options):
        filename = options['filename']
        backup_dir = settings.DBBACKUP_STORAGE_OPTIONS['location']
        backup_file = os.path.join(backup_dir, filename)
        
        if not os.path.exists(backup_file):
            raise CommandError(f"Backup file {filename} not found")
        
        # Get database connection info
        db_settings = settings.DATABASES['default']
        db_name = db_settings['NAME']
        db_user = db_settings.get('USER', '')
        db_password = db_settings.get('PASSWORD', '')
        db_host = db_settings.get('HOST', 'localhost')
        db_port = str(db_settings.get('PORT', '5432'))  # Ensure port is a string
        
        # Close all database connections
        connections.close_all()
        
        # Create environment with password
        env = os.environ.copy()
        if db_password:
            env['PGPASSWORD'] = db_password
        
        # First drop and recreate the database
        try:
            # Drop connections
            drop_conn_cmd = [
                'psql', 
                '-h', str(db_host), 
                '-p', str(db_port), 
                '-U', str(db_user), 
                '-d', 'postgres',
                '-c', f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db_name}'"
            ]
            subprocess.run(drop_conn_cmd, env=env, check=False)
            
            # Drop database
            drop_cmd = [
                'psql', 
                '-h', str(db_host), 
                '-p', str(db_port), 
                '-U', str(db_user), 
                '-d', 'postgres',
                '-c', f"DROP DATABASE IF EXISTS {db_name}"
            ]
            subprocess.run(drop_cmd, env=env, check=False)
            
            # Create database
            create_cmd = [
                'psql', 
                '-h', str(db_host), 
                '-p', str(db_port), 
                '-U', str(db_user), 
                '-d', 'postgres',
                '-c', f"CREATE DATABASE {db_name} WITH OWNER = {db_user}"
            ]
            subprocess.run(create_cmd, env=env, check=False)
            
            # Process the backup file to remove role-specific commands
            temp_file = os.path.join(backup_dir, f"temp_{filename}")
            with open(backup_file, 'r', encoding='utf-8', errors='ignore') as src, open(temp_file, 'w', encoding='utf-8') as dst:
                for line in src:
                    if 'ROLE "hello_django"' not in line and 'ALTER ROLE' not in line:
                        dst.write(line)
            
            # Restore from the processed file
            restore_cmd = [
                'psql', 
                '-h', str(db_host), 
                '-p', str(db_port), 
                '-U', str(db_user), 
                '-d', str(db_name),
                '-f', temp_file
            ]
            
            result = subprocess.run(restore_cmd, env=env, capture_output=True, text=True)
            
            # Clean up temp file
            if os.path.exists(temp_file):
                os.remove(temp_file)
                
            if result.returncode != 0:
                self.stderr.write(f"Error restoring database: {result.stderr}")
                raise CommandError(f"Failed to restore database: {result.stderr}")
            
            self.stdout.write(self.style.SUCCESS(f"Successfully restored database from {filename}"))
            
        except Exception as e:
            # Clean up temp file in case of error
            temp_file = os.path.join(backup_dir, f"temp_{filename}")
            if os.path.exists(temp_file):
                os.remove(temp_file)
            raise CommandError(f"Error during database restore: {str(e)}")

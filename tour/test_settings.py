# Run tests with: python manage.py test tours --settings=tour.test_settings
# The tours app keeps no migration files in git, so build every table straight from the models.
from .settings import *  # noqa


class _NoMigrations(dict):
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


MIGRATION_MODULES = _NoMigrations()
ALLOWED_HOSTS = ['*']

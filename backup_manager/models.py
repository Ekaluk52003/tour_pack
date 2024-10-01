# This file can be empty or you can remove it if you're not using any models in this app

from django.db import models

class BackupManagement(models.Model):
    class Meta:
        verbose_name = "Backup Management"
        verbose_name_plural = "Backup Management"

    def __str__(self):
        return "Backup Management"
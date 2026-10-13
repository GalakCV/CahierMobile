from django.db import models


class ImportLog(models.Model):
    """Registro de cada importação (aplicada, simulada ou recusada)."""

    class Status(models.TextChoices):
        APPLIED = "applied", "Aplicada"
        DRY_RUN = "dry_run", "Simulação"
        FAILED = "failed", "Recusada"

    created_at = models.DateTimeField("data", auto_now_add=True)
    filename = models.CharField("arquivo", max_length=255)
    status = models.CharField("resultado", max_length=10, choices=Status.choices)
    update_existing = models.BooleanField("atualizar existentes", default=False)
    report = models.JSONField("relatório", default=dict)

    class Meta:
        verbose_name = "importação"
        verbose_name_plural = "importações"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.filename} ({self.get_status_display()})"

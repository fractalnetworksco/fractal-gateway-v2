from typing import TYPE_CHECKING

from django.db import models, transaction
from fractal_database.models import Device, ReplicatedModel

if TYPE_CHECKING:
    from fractal.gateway.models import MatrixHomeserver


class Gateway(Device):
    homeservers: "models.QuerySet[MatrixHomeserver]"
    databases = models.ManyToManyField("fractal_database.Database", related_name="gateways")

    def __str__(self) -> str:
        return f"{self.name} (Gateway)"


class MatrixHomeserver(ReplicatedModel):
    url = models.URLField()
    name = models.CharField(max_length=255)
    gateway = models.ForeignKey(Gateway, on_delete=models.CASCADE, related_name="homeservers")
    priority = models.PositiveIntegerField(default=0, blank=True, null=True)
    database = models.ForeignKey("fractal_database.Database", on_delete=models.CASCADE)

    def __str__(self) -> str:
        return f"{self.name} - {self.url} (MatrixHomeserver)"

    def save(self, *args, **kwargs):
        # ensure that save is running in a transaction
        if not transaction.get_connection().in_atomic_block:
            with transaction.atomic():
                return self.save(*args, **kwargs)

        # priority is always set to the last priority + 1
        if self._state.adding:
            last_priority = MatrixHomeserver.objects.filter(gateway=self.gateway).aggregate(
                models.Max("priority")
            )["priority__max"]
            self.priority = (last_priority or 0) + 1

        return super().save(*args, **kwargs)


class Domain(ReplicatedModel):
    name = models.CharField(max_length=255)
    gateway = models.ManyToManyField(Gateway, related_name="domains")

    def __str__(self) -> str:
        return f"{self.name} (Domain)"


class Link(ReplicatedModel):
    domain = models.ForeignKey(Domain, on_delete=models.CASCADE)
    subdomain = models.CharField(max_length=255)

    def __str__(self) -> str:
        return f"{self.subdomain}.{self.domain} (Link)"

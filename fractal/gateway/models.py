from typing import TYPE_CHECKING

from django.db import models
from fractal_database.models import ReplicatedModel

if TYPE_CHECKING:
    from fractal.gateway.models import MatrixHomeserver
    from fractal_database.models import Database


class Gateway(ReplicatedModel):
    matrixhomeserver_set: "models.QuerySet[MatrixHomeserver]"

    name = models.CharField(max_length=255)
    database = models.ForeignKey("fractal_database.Database", on_delete=models.CASCADE)
    primary = models.BooleanField(default=False)

    class Meta:
        # enforce constraint that only allows a single primary for a given database
        constraints = [
            models.UniqueConstraint(
                fields=["database"],
                condition=models.Q(primary=True),
                name="%(app_label)s_%(class)s_unique_primary_gateway",
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} (Gateway)"

    def primary_homeserver(self, database: "Database") -> "MatrixHomeserver":
        from fractal_database_matrix.models import MatrixReplicationTarget

        primary_target: "MatrixReplicationTarget" = database.primary_target()  # type: ignore
        return self.matrixhomeserver_set.get(url=primary_target.homeserver)


class MatrixHomeserver(ReplicatedModel):
    url = models.URLField()
    name = models.CharField(max_length=255)
    gateway = models.ForeignKey(Gateway, on_delete=models.CASCADE)

    def __str__(self) -> str:
        return f"{self.name} - {self.url}"


class Link(ReplicatedModel):
    url = models.URLField()
    gateway = models.ForeignKey(Gateway, on_delete=models.CASCADE)

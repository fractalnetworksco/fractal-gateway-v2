import uuid
from typing import TYPE_CHECKING

from django.db import models, transaction
from fractal_database.models import App, ReplicatedModel
from fractal_database_matrix.models import MatrixReplicationTarget

if TYPE_CHECKING:
    from fractal.gateway.models import MatrixHomeserver


class Gateway(App):
    links: "models.QuerySet[Link]"
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


class Link(ReplicatedModel):
    id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    gateways = models.ManyToManyField(Gateway, related_name="links")
    fqdn = models.CharField(max_length=255)
    # TODO: needs an owner

    def __str__(self) -> str:
        return f"{self.fqdn} (Link)"


class GatewayReplicationTarget(MatrixReplicationTarget):
    class Meta:
        proxy = True

    def create_representation_logs(self, instance: ReplicatedModel):
        """
        Create the representation logs (tasks) for creating a Matrix space
        """
        from fractal_database.models import Database, RepresentationLog

        repr_logs = []
        repr_module = instance.get_representation_module()
        if not repr_module:
            return []
        repr_type = RepresentationLog._get_repr_instance(repr_module)

        if self == instance:
            # get primary target for the database so that we can add this created target as a subspace to it
            # this puts the user's gateway under their root database
            target: MatrixReplicationTarget = Database.current_db().primary_target()  # type: ignore
        else:
            target = self

        print(f"Creating repr {repr_type} logs for instance {instance} on target {target}")
        repr_logs.extend(repr_type.create_representation_logs(instance, target))
        return repr_logs

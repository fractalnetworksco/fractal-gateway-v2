import logging
import uuid
from typing import TYPE_CHECKING

import sh
from asgiref.sync import async_to_sync
from django.db import models
from fractal_database.models import Database, ReplicatedModel
from fractal_database.replication.tasks import replicate_fixture

from .tasks import link_up
from .utils import generate_link_compose_snippet

if TYPE_CHECKING:
    from .models import Gateway

logger = logging.getLogger(__name__)


class Link(ReplicatedModel):
    id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    gateways = models.ManyToManyField("fgateway.Gateway", related_name="links")
    fqdn = models.CharField(max_length=255, unique=True)
    service = models.ForeignKey(
        "fractal_database.ServiceInstanceConfig",
        on_delete=models.CASCADE,
        related_name="links",
        null=True,
        blank=True,
    )
    # TODO: needs an owner

    def __str__(self) -> str:
        return f"{self.fqdn} (Link)"

    def _up_via_ssh(self, ssh_config: dict[str, str]) -> tuple[str, str, str]:
        try:
            result = sh.ssh(
                ssh_config["host"], "-p", ssh_config["port"], "fractal link up", self.fqdn
            ).strip()
        except Exception as err:
            print(f"Error when running link up: {err.stderr.decode()}")
            raise err

        return result.split(",")

    def up(self, gateway: "Gateway") -> tuple[str, str, str]:
        if gateway.ssh_config:
            return self._up_via_ssh(gateway.ssh_config)
        else:
            return async_to_sync(link_up)(self.fqdn)

    def generate_compose_snippet(self, gateway: "Gateway", expose: str) -> str:
        gateway_link_public_key, link_address, client_private_key = self.up(gateway)

        if "localhost" in link_address:
            _, port = link_address.split(":")
            link_address = f"host.docker.internal:{port}"

        return generate_link_compose_snippet(
            {
                "gateway_link_public_key": gateway_link_public_key,
                "link_address": link_address,
                "client_private_key": client_private_key,
            },
            self.fqdn,
            expose,
        )


class Gateway(Database):
    links: models.QuerySet[Link]
    # homeservers: "models.QuerySet[MatrixHomeserver]"

    databases = models.ManyToManyField("fractal_database.Database", related_name="gateways")
    ssh_config = models.JSONField(default=dict)

    def __str__(self) -> str:
        return f"{self.name} (Gateway)"

    def _create_link_via_ssh(self, link_fqdn: str, override_link: bool = False) -> Link:
        """
        Intended to be run when the gateway is being interacted with remotely.
        """
        from fractal.gateway.models import Link

        ssh_host = self.ssh_config["host"]
        ssh_port = self.ssh_config["port"]  # type: ignore
        try:
            result = sh.ssh(
                ssh_host,
                "-p",
                str(ssh_port),
                f"fractal link create {link_fqdn} {self.name} --output-as-json",
                "--override" if override_link else "",
            )
        except Exception as err:
            raise Exception("Failed to create link via SSH: %s" % err.stderr.decode()) from err

        try:
            async_to_sync(replicate_fixture)(result.strip())
        except Exception as e:
            print(f"Error replicating link: {e}")
            exit(1)

        return Link.objects.get(fqdn=link_fqdn)

    def create_link(self, fqdn: str, override_link: bool = False) -> Link:
        try:
            link = Link.objects.get(fqdn=fqdn)
            if not override_link:
                raise Exception(
                    f"Link {fqdn} already exists. Specify --override to forcefully override."
                )
        except Link.DoesNotExist:
            if self.ssh_config:
                # create via ssh
                link = self._create_link_via_ssh(fqdn, override_link=override_link)

            else:
                link = Link.objects.create(fqdn=fqdn)

        link.gateways.add(self)

        return link


# class MatrixHomeserver(ReplicatedModel):
#     url = models.URLField()
#     name = models.CharField(max_length=255)
#     gateway = models.ForeignKey(Gateway, on_delete=models.CASCADE, related_name="homeservers")
#     priority = models.PositiveIntegerField(default=0, blank=True, null=True)
#     database = models.ForeignKey("fractal_database.Database", on_delete=models.CASCADE)

#     def __str__(self) -> str:
#         return f"{self.name} - {self.url} (MatrixHomeserver)"

#     def save(self, *args, **kwargs):
#         # ensure that save is running in a transaction
#         if not transaction.get_connection().in_atomic_block:
#             with transaction.atomic():
#                 return self.save(*args, **kwargs)

#         # priority is always set to the last priority + 1
#         if self._state.adding:
#             last_priority = MatrixHomeserver.objects.filter(gateway=self.gateway).aggregate(
#                 models.Max("priority")
#             )["priority__max"]
#             self.priority = (last_priority or 0) + 1

#         return super().save(*args, **kwargs)

import json
import logging
import sys
import uuid
from typing import TYPE_CHECKING, Optional

import docker
import yaml
from asgiref.sync import async_to_sync
from django.db import models
from django.db.models import Q
from docker.errors import NotFound
from fractal_database import ssh
from fractal_database.fields import LocalJSONField, LocalManyToManyField
from fractal_database.models import Device, ReplicatedModel, Service
from fractal_database.replication.tasks import replicate_fixture

from .tasks import link_up
from .utils import GATEWAY_RESOURCE_PATH, generate_link_compose_snippet

if TYPE_CHECKING:
    from fractal_database_matrix.models import MatrixReplicationChannel

    from .models import Gateway, Link

logger = logging.getLogger(__name__)


class Domain(ReplicatedModel):
    links: models.QuerySet["Link"]

    uri = models.CharField(max_length=255, unique=True)
    devices = models.ManyToManyField("fractal_database.Device", related_name="domains")


class Link(ReplicatedModel):
    id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    # gateways = models.ManyToManyField("gateway.Gateway", related_name="links")
    domain = models.ForeignKey(Domain, on_delete=models.CASCADE, related_name="domains")
    service = models.ForeignKey(
        "fractal_database.ServiceInstanceConfig",
        on_delete=models.CASCADE,
        related_name="links",
        null=True,
        blank=True,
    )
    subdomain = models.CharField(max_length=255)

    # TODO: needs an owner

    def __str__(self) -> str:
        return self.fqdn

    @property
    def fqdn(self) -> str:
        return f"{self.subdomain}.{self.domain.uri}"

    def _up_via_ssh(self, gateway: "Gateway", device: "Device") -> tuple[str, str, str]:
        ssh_config = device.ssh_config
        try:
            result = ssh(
                ssh_config["host"],
                "-p",
                ssh_config["port"],
                f"fractal link up {str(gateway.pk)} {self.fqdn}",
            ).strip()
        except Exception as err:
            print(f"Error when running link up: {err.stderr.decode()}")
            raise err

        return result.split(",")

    async def up(self, gateway: "Gateway") -> tuple[str, str, str]:
        membership = (
            await gateway.device_memberships.select_related("device")
            .prefetch_related("device__domains")
            .filter(~Q(device__ssh_config={}), device__domains__pk=self.domain.pk)
            .afirst()
        )
        if membership:
            return self._up_via_ssh(gateway, membership.device)
        else:
            channel: Optional["MatrixReplicationChannel"] = await gateway.matrixreplicationchannel_set.afirst()  # type: ignore
            if not channel:
                raise Exception(
                    f"Gateway {gateway.name} does not have a matrix replication channel"
                )

            # fetch a device membership where the device has this link's domain in its domains
            membership = (
                await gateway.device_memberships.select_related("device")
                .prefetch_related("device__domains")
                .filter(device__domains__pk=self.domain.pk)
                .afirst()
            )
            if not membership:
                raise Exception(
                    f"Could not find a device for gateway {gateway.name} that serves the fqdn {self.fqdn}"
                )

            task_labels = {
                "device": membership.device.name,
            }

            task = await channel.kick_task(link_up, self.fqdn, task_labels=task_labels)
            result = await task.wait_result()
            return result.return_value

    def generate_compose_snippet(self, gateway: "Gateway", expose: str) -> str:
        gateway_link_public_key, link_address, client_private_key = async_to_sync(self.up)(
            gateway
        )
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


class Gateway(Service):
    links: models.QuerySet[Link]
    # homeservers: "models.QuerySet[MatrixHomeserver]"
    COMPOSE_FILE = f"{GATEWAY_RESOURCE_PATH}/docker-compose.yml"

    databases = LocalManyToManyField("fractal_database.Database", related_name="gateways")

    def __str__(self) -> str:
        return f"{self.name} (Gateway)"

    def _create_gateway_docker_network(self) -> None:
        client = docker.from_env()
        try:
            network = client.networks.get("fractal-gateway-network")  # type: ignore
        except NotFound:
            network = client.networks.create("fractal-gateway-network", driver="bridge")  # type: ignore
        return network

    def _render_compose_file(self) -> str:
        # ensure docker network for gateway is created
        self._create_gateway_docker_network()

        with open(self.COMPOSE_FILE) as f:
            compose_file = yaml.safe_load(f)

        # update f.gateway label to have the gateway's primary key
        compose_file["services"]["gateway"]["labels"]["f.gateway"] = str(self.pk)

        return yaml.dump(compose_file)

    def get_domain(self, domain: str) -> Domain:
        return Domain.objects.prefetch_related(
            "devices__memberships", "devices__memberships__database"
        ).get(uri=domain, devices__memberships__database=self)

    def get_domains(self) -> models.QuerySet[Domain]:
        return Domain.objects.prefetch_related(
            "devices__memberships", "devices__memberships__database"
        ).filter(devices__memberships__database=self)

    def _create_link_via_ssh(
        self, domain: Domain, subdomain: str, device: "Device", override_link: bool = False
    ) -> Link:
        """
        Intended to be run when the gateway is being interacted with remotely.
        """
        from fractal.gateway.models import Link

        ssh_host = device.ssh_config["host"]
        ssh_port = device.ssh_config["port"]  # type: ignore

        try:
            result = ssh(
                ssh_host,
                "-p",
                str(ssh_port),
                f"fractal link create {subdomain}.{domain.uri} {str(self.pk)} --output-as-json",
                "--force" if override_link else "",
            )
        except Exception as err:
            raise Exception("Failed to create link via SSH: %s" % err.stderr.decode()) from err

        event = json.dumps(
            {
                "replication_id": str(uuid.uuid4()),
                "payload": json.loads(result.strip()),
            }
        )

        try:
            async_to_sync(replicate_fixture)(event, None)
        except Exception as e:
            print(f"Error replicating link: {e}", file=sys.stderr)
            exit(1)

        return Link.objects.get(domain=domain, subdomain=subdomain)

    def create_link(self, domain: Domain, subdomain: str, override_link: bool = False) -> Link:
        with self.as_current_database():
            try:
                link = Link.objects.get(domain=domain, subdomain=subdomain)
                if not override_link:
                    raise Exception(
                        f"Link {link} already exists. Specify --override to forcefully override."
                    )
            except Link.DoesNotExist:
                # get all devices that have the fqdn
                memberships = (
                    self.device_memberships.prefetch_related("device__domains")
                    .select_related("device")
                    .filter(device__domains__pk=domain.pk)
                )
                if not memberships.exists():
                    raise Exception(
                        f"Gateway {self} does not have any devices that serve domain {domain}"
                    )

                # if any memberships that have devices with ssh_config, create the link by sshing to that device
                membership_with_ssh_config = memberships.filter(~Q(device__ssh_config={})).first()

                if membership_with_ssh_config:
                    link = self._create_link_via_ssh(
                        domain,
                        subdomain,
                        membership_with_ssh_config.device,
                        override_link=override_link,
                    )
                else:
                    link = Link.objects.create(domain=domain, subdomain=subdomain)

            # link.gateways.add(self)
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

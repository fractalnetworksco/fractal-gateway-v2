import json
import logging
import os
import sys
import uuid
from typing import TYPE_CHECKING, Optional

import docker
import tldextract
import yaml
from asgiref.sync import async_to_sync
from django.db import models, transaction
from django.db.models import Q
from docker.errors import NotFound
from fractal_database import ssh
from fractal_database.fields import LocalManyToManyField
from fractal_database.models import (
    DatabaseConfig,
    DatabaseMembership,
    Device,
    ReplicatedModel,
    Service,
)
from fractal_database.replication.tasks import replicate_fixture

from .tasks import link_up
from .utils import (
    GATEWAY_RESOURCE_PATH,
    build_gateway_containers,
    generate_link_compose_snippet,
)

if TYPE_CHECKING:
    from fractal_database.models import Database
    from fractal_database_matrix.models import MatrixReplicationChannel

    from .models import Gateway, Link

logger = logging.getLogger(__name__)


class Domain(ReplicatedModel):
    links: models.QuerySet["Link"]

    uri = models.CharField(max_length=255, unique=True)
    devices = models.ManyToManyField("fractal_database.Device", related_name="domains")

    def __str__(self) -> str:
        return self.uri


class Link(ReplicatedModel):
    id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    # gateways = models.ManyToManyField("gateway.Gateway", related_name="links")
    domain = models.ForeignKey(Domain, on_delete=models.CASCADE, related_name="domains")
    service_config = models.ForeignKey(
        "fractal_database.ServiceInstanceConfig",
        on_delete=models.CASCADE,
        related_name="links",
        null=True,
        blank=True,
    )
    subdomain = models.CharField(max_length=255)
    forward_port = models.CharField(max_length=5, null=True, blank=True)

    # TODO: needs an owner

    @classmethod
    def get_by_url(cls, url: str, select_related: Optional[list[str]] = None) -> "Link":
        extracted_url = tldextract.extract(url)
        # registered_domains have the domain + suffix joined together.
        # some domains like localhost don't have a registered domain (dont have a suffix)
        # so if registered_domain is "" then use the domain
        domain = extracted_url.registered_domain or extracted_url.domain
        subdomain = extracted_url.subdomain

        if "." in subdomain:
            subdomain, to_add = subdomain.split(".", 1)
            domain = f"{to_add}.{domain}"

        if select_related:
            return cls.objects.select_related(*select_related).get(
                domain__uri=domain, subdomain=subdomain
            )

        return cls.objects.get(domain__uri=domain, subdomain=subdomain)

    @classmethod
    async def aget_by_url(cls, url: str, select_related: Optional[list[str]] = None) -> "Link":
        extracted_url = tldextract.extract(url)
        # registered_domains have the domain + suffix joined together.
        # some domains like localhost don't have a registered domain (dont have a suffix)
        # so if registered_domain is "" then use the domain
        domain = extracted_url.registered_domain or extracted_url.domain
        subdomain = extracted_url.subdomain

        if "." in subdomain:
            subdomain, to_add = subdomain.split(".", 1)
            domain = f"{to_add}.{domain}"

        if select_related:
            return await cls.objects.select_related(*select_related).aget(
                domain__uri=domain, subdomain=subdomain
            )

        return await cls.objects.aget(domain__uri=domain, subdomain=subdomain)

    def __str__(self) -> str:
        return self.fqdn

    @property
    def fqdn(self) -> str:
        if not self.subdomain:
            return self.domain.uri
        return f"{self.subdomain}.{self.domain.uri}"

    async def _up_local(self, tcp_forwarding: bool) -> tuple[str, str, str, str]:
        return await link_up(
            self.fqdn, tcp_forwarding=tcp_forwarding, forward_port=self.forward_port
        )

    def _up_via_ssh(
        self, gateway: "Gateway", device: "Device", tcp_forwarding: bool = False
    ) -> tuple[str, str, str, str]:
        link_up_command = f"fractal link up {str(gateway.pk)} {self.fqdn}"
        if tcp_forwarding:
            link_up_command += " --tcp-forwarding"
        if self.forward_port:
            link_up_command += f" --forward-port {self.forward_port}"

        ssh_config = device.ssh_config
        try:
            result = ssh(ssh_config["host"], "-p", ssh_config["port"], link_up_command).strip()
        except Exception as err:
            print(f"Error when running link up: {err.stderr.decode()}")
            raise err

        return result.split(",")

    def gateway_is_local(self, gateway: "Gateway") -> bool:
        client = docker.from_env()
        return len(client.containers.list(filters={"label": f"f.gateway={str(gateway.pk)}"})) > 0

    async def up(self, gateway: "Gateway", tcp_forwarding: bool = False) -> tuple[str, str, str]:
        # get a device membership where the device has ssh_config to gateway
        membership = (
            await gateway.device_memberships.select_related("device")
            .prefetch_related("device__domains")
            .filter(~Q(device__ssh_config={}), device__domains__pk=self.domain.pk)
            .afirst()
        )
        # link up via ssh if a device with ssh_config to gateway is found
        if membership:
            gateway_link_public_key, link_address, client_private_key, forward_port = (
                self._up_via_ssh(gateway, membership.device, tcp_forwarding=tcp_forwarding)
            )

        # link_up directly if the gateway is local
        elif self.gateway_is_local(gateway):
            gateway_link_public_key, link_address, client_private_key, forward_port = (
                await link_up(
                    self.fqdn, tcp_forwarding=tcp_forwarding, forward_port=self.forward_port
                )
            )

        # link_up via a matrix replication channel if the gateway is remote
        # and has a matrix replication channel
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

            logger.info(
                "Kicking link up task for %s to device %s to channel %s",
                self.fqdn,
                membership.device.name,
                channel,
            )
            # kick link up task as user to the gateway device
            task = await channel.kick_task(
                link_up,
                self.fqdn,
                tcp_forwarding,
                self.forward_port,
                task_labels=task_labels,
                as_user=True,
            )
            logger.info("Waiting for %s link up result for up to 2 minutes..." % self.fqdn)
            result = await task.wait_result(timeout=120.0)
            logger.info("Link up for %s took %s seconds" % (self.fqdn, result.execution_time))

            if result.is_err:
                raise Exception(f"Error when running link up: {result.err}")

            gateway_link_public_key, link_address, client_private_key, forward_port = (
                result.return_value
            )

        # save forward port to the link for subsequent use
        self.forward_port = forward_port
        await self.asave()

        return (gateway_link_public_key, link_address, client_private_key)

    def generate_compose_snippet(
        self, gateway: "Gateway", expose: str, tcp_forwarding: bool = False
    ) -> str:
        gateway_link_public_key, link_address, client_private_key = async_to_sync(self.up)(
            gateway, tcp_forwarding=tcp_forwarding
        )
        if "localhost" in link_address:
            _, port = link_address.split(":")
            link_address = f"host.docker.internal:{port}"

        new_forwarding = False
        if expose.startswith("tcp://"):
            expose = expose.replace("tcp://", "").split(":", maxsplit=1)[1]
            new_forwarding = True
        elif expose.startswith("udp://"):
            expose = expose.replace("udp://", "").split(":", maxsplit=1)[1]
            new_forwarding = True

        link_config = {
            "gateway_link_public_key": gateway_link_public_key,
            "link_address": link_address,
            "client_private_key": client_private_key,
        }

        return generate_link_compose_snippet(
            link_config,
            self.fqdn,
            expose,
            new_forwarding=new_forwarding,
        )


class Gateway(Service):
    links: models.QuerySet[Link]
    # homeservers: "models.QuerySet[MatrixHomeserver]"
    COMPOSE_FILE = os.environ.get(
        "GATEWAY_COMPOSE_PATH", f"{GATEWAY_RESOURCE_PATH}/docker-compose.yml"
    )

    # FIXME: MOVE TO DATABASE
    databases = LocalManyToManyField("fractal_database.Database", related_name="gateways")

    def __str__(self) -> str:
        return f"{self.name} (Gateway)"

    @classmethod
    def create_service(cls, database: "Database") -> "Gateway":
        """
        Create the gateway service for a given database.
        Returns the created gateway service.
        """
        with transaction.atomic():
            with database.as_current_database(threadlocal=True):
                # fetch the root database to get all actual gateway services
                # doing it this way instead of Database.current_db() since the current_db
                # could be set using a threadlocal. Whatever is in the DatabaseConfig is the
                # actual database that is being used
                root_database = (
                    DatabaseConfig.objects.select_related("current_db").get().current_db
                )

                # fetch the gateway services
                # these are considered to be Gateways whose parent_db is that of the root database
                gateways = cls.objects.filter(parent_db=root_database)
                if not gateways:
                    raise Gateway.DoesNotExist("No gateways found in the current root database")

                # get all gateway devices
                gateway_devices = (
                    Device.objects.prefetch_related("memberships", "memberships__database")
                    .filter(memberships__database__in=gateways)
                    .distinct()
                )

                # get all devices that are members of the created group
                group_devices = (
                    Device.objects.prefetch_related("memberships", "memberships__database")
                    .filter(memberships__database=database)
                    .distinct()
                )

                # combine the two querysets and removes any duplicates
                devices_to_add_to_gateway_service = gateway_devices.union(
                    group_devices, all=False
                )

                # create the gateway service for the provided database
                gateway_service = cls.objects.create(
                    name=f"{database.name}_gateway",
                )

                # add all gateway devices and database devices to the gateway service
                if devices_to_add_to_gateway_service:
                    for device in devices_to_add_to_gateway_service:
                        device.add_membership(gateway_service)

                # add all users to the gateway service
                for member in database.users:
                    member.add_membership(gateway_service)

                gateway_service.databases.add(database)

                return gateway_service

    def _create_gateway_docker_network(self) -> None:
        client = docker.from_env()
        try:
            network = client.networks.get("fractal-gateway-network")  # type: ignore
        except NotFound:
            network = client.networks.create("fractal-gateway-network", driver="bridge")  # type: ignore
        return network

    def _build_containers(self) -> None:
        return build_gateway_containers()

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
        with self.as_current_database(threadlocal=True):
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

    @classmethod
    def get_or_create_service(cls, database: "Database") -> tuple["Gateway", bool]:
        try:
            gateway = cls.objects.get(parent_db=database)
            return gateway, False
        except cls.DoesNotExist:
            return cls.create_service(database), True


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

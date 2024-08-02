import asyncio
import json
import os
import sys
import traceback
import uuid
from typing import TYPE_CHECKING, Optional

from asgiref.sync import async_to_sync
from clicz import cli_method
from django.db import transaction
from django.db.models import Q, Subquery
from fractal.cli.fmt import display_data
from fractal.gateway.exceptions import PortAlreadyAllocatedError
from fractal.gateway.utils import check_port_availability, launch_gateway
from fractal_database import ssh
from fractal_database.controllers.fractal_database_controller import (
    FractalDatabaseController,
)
from fractal_database.utils import is_db_initialized, use_django

if TYPE_CHECKING:
    from fractal_database.models import Device


class FractalGatewayController:
    PLUGIN_NAME = "gateway"
    HTTP_GATEWAY_PORT = 80
    HTTPS_GATEWAY_PORT = 443

    @use_django
    @cli_method
    def export(
        self,
        gateway_name: str = "fractal-gateway",
        format: str = "json",
        silent: bool = False,
        **kwargs,
    ):
        """
        ---
        Args:
            gateway_name: The name of the Gateway to export. Defaults to "fractal-gateway".
            format: The format to export the Gateway in. Options are "json" or "python". Defaults to "json".
            silent: If True, the output will not be printed to stdout. Defaults to False.
        """
        from fractal.gateway.models import Gateway

        try:
            gateway = Gateway.objects.get(name__icontains=gateway_name)
        except Gateway.DoesNotExist:
            print(f"Gateway {gateway_name} does not exist.")
            exit(1)

        match format:
            case "json":
                gateway_fixture = gateway.to_fixture(with_relations=True, json=True)
                gateway_fixture = json.loads(gateway_fixture)
                gateway_fixture = {
                    "replication_id": str(uuid.uuid4()),
                    "payload": [*gateway_fixture],
                }

                # include device memberships in the fixture
                device_memberships = gateway.device_memberships.prefetch_related(
                    "device__domains"
                ).all()
                for membership in device_memberships:
                    gateway_fixture["payload"].extend(
                        json.loads(membership.to_fixture(with_relations=True, json=True))
                    )
                    domains = membership.device.domains.all()
                    for domain in domains:
                        gateway_fixture["payload"].extend(
                            json.loads(domain.to_fixture(with_relations=True, json=True))
                        )

                gateway_fixture = json.dumps(gateway_fixture)

            case "python":
                gateway_fixture = gateway.to_fixture(with_relations=True, queryset=True)
                gateway_fixture = {
                    "replication_id": str(uuid.uuid4()),
                    "payload": [*gateway_fixture],
                }
                for membership in gateway.device_memberships.all():
                    gateway_fixture["payload"].extend(
                        membership.to_fixture(with_relations=True, queryset=True)
                    )

            case _:
                print(f"Invalid format: {format}", file=sys.stderr)
                exit(1)

        if not silent:
            print(gateway_fixture)

        return gateway_fixture

    @use_django
    @cli_method
    def list(self, format: str = "table", **kwargs):
        """
        List Gateways.
        ---
        Args:
            format: The format to display the data in. Options are "table" or "json". Defaults to "table".
        """
        from fractal.gateway.models import Gateway

        gateways = Gateway.objects.all()
        if not gateways.exists():
            print("No gateways found")
            exit(0)

        data = [{"id": str(gateway.pk), "name": gateway.name} for gateway in gateways]
        display_data(data, title="Gateways", format=format)

    @use_django
    def _init(self, gateway_name: str, fqdn: str, **kwargs):
        from fractal.gateway.models import Gateway
        from fractal.gateway.signals import create_gateway_and_homeserver_for_current_db

        gateway_name = "fractal-gateway"
        try:
            Gateway.objects.get(name__icontains=gateway_name)
            print(f"Gateway {gateway_name} already exists.", file=sys.stderr)
            exit(1)
        except Gateway.DoesNotExist:
            pass

        # verify that the Gateway port is available
        try:
            check_port_availability(self.HTTP_GATEWAY_PORT)
            check_port_availability(self.HTTPS_GATEWAY_PORT)
        except PortAlreadyAllocatedError as err:
            print(f"Can't initialize Gateway: Port {err.port} is already taken.", file=sys.stderr)
            exit(1)
        except Exception as err:
            print(
                f"Can't initialize Gateway: Failed to verify port availability: {err}",
                file=sys.stderr,
            )
            exit(1)

        try:
            gateway = create_gateway_and_homeserver_for_current_db(gateway_name, fqdn)
        except Exception:
            traceback.print_exc()
            exit(1)

        # launch docker container, pass unique gateway name as label for easy retrieval
        print(f"Successfully initialized and launched Gateway: {gateway_name}")

    @use_django
    def _init_remote(self, ssh_url: str, ssh_port: str, fqdn: str, gateway_name: str, **kwargs):
        from fractal_database.models import Database

        try:
            result = ssh(ssh_url, "-p", ssh_port, f"fractal gateway init {fqdn} --gateway-name {gateway_name}")  # type: ignore
        except Exception as err:
            print(f"Failed to initialize Gateway:\n{err.stderr.decode()}", file=sys.stderr)
            exit(1)

        print("Loading remote gateway into local database")

        current_database = Database.current_db()
        return self._add_via_ssh(ssh_url, current_database.name, ssh_port=ssh_port)

    @cli_method
    def init(
        self,
        fqdn: str,
        gateway_name: str = "fractal_gateway",
        ssh_url: Optional[str] = None,
        ssh_port: str = "22",
        **kwargs,
    ):
        """
        Initializes the current Device as a Gateway. Can optionally be initialized remotely via SSH.
        When initializing remotely, the Gateway will be loaded into your current database.
        NOTE: When initializing remotely, ensure that you are able to SSH into the remote machine.
        ---
        Args:
            fqdn: The fqdn the Gateway can create links under.
            gateway_name: The name of the Gateway to initialize. Defaults to "fractal_gateway".
            ssh_url: The SSH URL of the Gateway. If provided, the Gateway will be initialized remotely, then loaded
                     into your current database.
            ssh_port: The SSH port of the Gateway. Defaults to 22.
        """
        if ssh_url:
            return self._init_remote(ssh_url, ssh_port, fqdn, gateway_name)

        # initialize the Fractal Database if it doesn't exist
        if not is_db_initialized():
            fdb_controller = FractalDatabaseController()
            fdb_controller.init(
                project_name=gateway_name, quiet=True, exist_ok=True, as_instance=True
            )

        self._init(gateway_name, fqdn)  # type: ignore

    @use_django
    @cli_method
    def launch(self, **kwargs):
        """
        Launches a Gateway.
        ---
        """
        from fractal.gateway.models import Gateway
        from fractal_database.models import Device, ServiceInstanceConfig

        try:
            gateway = Gateway.objects.get(name__icontains="fractal-gateway")
        except Gateway.DoesNotExist:
            print("Gateway does not exist. Run `fractal gateway init` to get started.")
            exit(1)

        try:
            conf = ServiceInstanceConfig.objects.get(service=gateway)
        except ServiceInstanceConfig.DoesNotExist:
            print(
                f"Failed to find service instance config for gateway: {gateway}", file=sys.stderr
            )
            exit(1)

        try:
            current_device = Device.current_device()
        except Device.DoesNotExist:
            print("No current device found.", file=sys.stderr)
            exit(1)

        conf.target_state = "running"
        conf.current_device = current_device
        conf.save()

    def _add_via_ssh(self, gateway_ssh: str, database_name: str, ssh_port: str = "22", **kwargs):
        from fractal.gateway.models import Gateway
        from fractal_database.models import Database, Device, LocalReplicationChannel
        from fractal_database.replication.tasks import replicate_fixture

        try:
            database = Database.objects.get(name=database_name)
        except Database.DoesNotExist:
            print(f"Database {database_name} does not exist.")
            exit(1)

        current_device = Device.current_device()

        with database.as_current_database():
            try:
                result = ssh(gateway_ssh, "-p", str(ssh_port), "fractal gateway export")
            except Exception as err:
                print(f"Failed to connect to Gateway:\n{err.stderr.decode()}", file=sys.stderr)
                exit(1)

            print("Syncing Gateway into local database")
            gateway_replication_event = json.loads(result.strip())
            for item in gateway_replication_event["payload"]:
                if item["model"] == "gateway.gateway":
                    gateway_uuid = item["pk"]
                    break
            else:
                # should never happen
                print(
                    f"Gateway did not return a gateway fixture:\n{json.dumps(gateway_replication_event, indent=4)}",
                    file=sys.stderr,
                )
                exit(1)

            # check to see if the gateway has already been loaded once into the local database
            try:
                gateway = Gateway.objects.get(pk=gateway_uuid)
            except Gateway.DoesNotExist:
                asyncio.run(replicate_fixture(json.dumps(gateway_replication_event), None))
                gateway = Gateway.objects.get(pk=gateway_uuid)
                LocalReplicationChannel.objects.get_or_create(
                    name=f"dummy-{gateway.name}", database=gateway
                )
                gateway_device_memberships = gateway.device_memberships.select_related(
                    "device"
                ).all()

                for membership in gateway_device_memberships:
                    print(f"Setting ssh config for Gateway device {membership.device.name}")
                    membership.device.ssh_config["host"] = gateway_ssh
                    membership.device.ssh_config["port"] = ssh_port
                    membership.device.save()

            gateway.databases.add(database)
            gateway.save()
            current_device.add_membership(gateway)

        print(f"Added Database {database.name} to Gateway {gateway.name}")

    @use_django
    @cli_method
    def add(self, gateway: str, database_name: str, ssh_port: str = "22", **kwargs):
        """
        Add a Database to a Gateway.
        ---
        Args:
            gateway: The SSH URL of the Gateway. Assumes that you have SSH access to the Gateway.
            database_name: Name of the Database to add
            ssh_port: The SSH port of the Gateway. Defaults to 22.
        """
        if not gateway.startswith("ssh://"):
            print("FIXME: Implement adding a gateway not through ssh")
            exit(1)

        self._add_via_ssh(gateway, database_name, ssh_port=ssh_port)

    @use_django
    @cli_method
    def register(self, gateway_name: str, database_name: str, **kwargs):
        """
        Creates a dedicated account for the Gateway on the homeserver you
        are replicating to.
        ---
        Args:
            gateway_name: Name of the Gateway.
            database_name: Name of the Database to register the Gateway as a service with.
        """
        from fractal.gateway.models import Gateway
        from fractal_database.models import Database, Device, LocalReplicationChannel
        from fractal_database_matrix.models import MatrixReplicationChannel

        # attempt to fetch gateway and its ssh config
        try:
            gateway = Gateway.objects.get(name__icontains=gateway_name)
        except Gateway.DoesNotExist:
            print(f"Gateway {gateway_name} does not exist.")
            exit(1)

        # FIXME: for now, any device that has an ssh_config is considered a gateway device
        gateway_device_memberships = gateway.device_memberships.select_related("device").filter(
            ~Q(device__ssh_config={})
        )
        if not gateway_device_memberships.exists():
            print(
                f"Cannot register gateway: {gateway.name}. No gateway devices have an SSH configuration.",
                file=sys.stderr,
            )
            exit(1)

        gateway_devices = set(
            gateway_device.device for gateway_device in gateway_device_memberships
        )

        try:
            database = Database.objects.get(name=database_name)
        except Database.DoesNotExist:
            print(f"Database {database_name} does not exist.", file=sys.stderr)
            exit(1)

        channels = database.get_all_replication_channels()

        homeservers = set()
        for channel in channels:
            if isinstance(channel, LocalReplicationChannel):
                continue
            if not isinstance(channel, MatrixReplicationChannel):
                continue

            homeservers.add(channel.homeserver)

        with database.as_current_database(use_transaction=True):
            # create the gateway service for the database (group)
            gateway_service = Gateway.objects.create(
                name=f"{database.name}-gateway", parent_db=database
            )

            # get all devices that are members of the gateway and database
            device_ids = (
                gateway.device_memberships.values_list("device", flat=True)
                | database.device_memberships.values_list("device", flat=True)
            ).distinct()
            devices = Device.objects.filter(pk__in=Subquery(device_ids))

            for device in devices:
                device.add_membership(gateway_service)

            # create matrix replication channels for each homeserver
            # for the gateway service
            for homeserver in homeservers:
                gateway_service.create_channel(
                    MatrixReplicationChannel, homeserver=homeserver, source=True, target=True
                )

        # now that the device should be registered with all homeservers,
        replication_event = {
            "replication_id": str(uuid.uuid4()),
            "payload": [],
        }
        # provide the gateway serivce itself
        replication_event["payload"].extend(
            json.loads(gateway_service.to_fixture(with_relations=True, json=True))
        )

        # provide all of the replication channels for the new gateway service
        for channel in gateway_service.get_all_replication_channels():
            replication_event["payload"].extend(
                json.loads(channel.to_fixture(with_relations=True, json=True))
            )

        # provide all of the gateway_service memberships
        for membership in gateway_service.device_memberships.all():
            replication_event["payload"].extend(
                json.loads(membership.to_fixture(with_relations=True, json=True))
            )

        # for each device, provide all of their respective matrix credentials
        for gateway_device in gateway_devices:
            device_replication_event = replication_event.copy()
            import pdb

            pdb.set_trace()
            for cred in gateway_device.matrixcredentials_set.all():
                device_replication_event["payload"].extend(
                    json.loads(cred.to_fixture(with_relations=True, json=True))
                )

            device_replication_event = json.dumps(device_replication_event)

            # load the replication event into the gateway
            try:
                result = ssh(
                    gateway_device.ssh_config["host"],
                    "-p",
                    str(gateway_device.ssh_config["port"]),
                    "fractal db sync -",
                    _in=device_replication_event,
                )
            except Exception as err:
                print(f"Failed to connect to Gateway:\n{err.stderr.decode()}", file=sys.stderr)
                exit(1)

        print(f"Successfully registered Gateway {gateway.name} for {database.name}")


Controller = FractalGatewayController

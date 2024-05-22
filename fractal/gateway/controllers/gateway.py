import asyncio
import json
import traceback

import sh
from clicz import cli_method
from fractal.cli.fmt import display_data
from fractal.gateway.exceptions import PortAlreadyAllocatedError
from fractal.gateway.utils import check_port_availability, launch_gateway
from fractal_database.controllers.fractal_database_controller import (
    FractalDatabaseController,
)
from fractal_database.utils import use_django


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
                gateway_fixture = gateway.to_fixture(json=True, with_relations=True)
            case "python":
                gateway_fixture = gateway.to_fixture(with_relations=True)
            case _:
                print(f"Invalid format: {format}")
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

        data = [{"name": gateway.name} for gateway in gateways]
        display_data(data, title="Gateways", format=format)

    @use_django
    def _init(self, gateway_name: str, **kwargs):
        from fractal.gateway.models import Gateway
        from fractal.gateway.signals import create_gateway_and_homeserver_for_current_db

        gateway_name = "fractal-gateway"
        try:
            Gateway.objects.get(name__icontains=gateway_name)
            print(f"Gateway {gateway_name} already exists.")
            exit(1)
        except Gateway.DoesNotExist:
            pass

        # verify that the Gateway port is available
        try:
            check_port_availability(self.HTTP_GATEWAY_PORT)
            check_port_availability(self.HTTPS_GATEWAY_PORT)
        except PortAlreadyAllocatedError as err:
            print(f"Can't initialize Gateway: Port {err.port} is already taken.")
            exit(1)
        except Exception as err:
            print(f"Can't initialize Gateway: Failed to verify port availability: {err}")
            exit(1)

        try:
            gateway = create_gateway_and_homeserver_for_current_db(gateway_name)
        except Exception:
            traceback.print_exc()
            exit(1)

        # launch docker container, pass unique gateway name as label for easy retrieval
        launch_gateway(gateway_name, labels={"f.gateway": str(gateway.pk)})

        print(f"Successfully initialized and launched Gateway: {gateway_name}")

    @cli_method
    def init(self, gateway_name: str = "fractal_gateway", **kwargs):
        """
        Initializes the current Device as a Gateway.
        ---
        Args:
            gateway_name: The name of the Gateway to initialize. Defaults to "fractal_gateway".
        """
        # attempt to fetch gateway. Exit if it already exists
        fdb_controller = FractalDatabaseController()
        fdb_controller.init(
            project_name=gateway_name, quiet=True, exist_ok=True, as_instance=True
        )

        self._init(gateway_name)  # type: ignore

    @use_django
    @cli_method
    def launch(self, **kwargs):
        """
        Launches a Gateway.
        ---
        """
        from fractal.gateway.models import Gateway

        try:
            gateway = Gateway.objects.get(name__icontains="fractal-gateway")
        except Gateway.DoesNotExist:
            print("Gateway does not exist. Run `fractal gateway init` to get started.")
            exit(1)

        try:
            launch_gateway(gateway.name, labels={"f.gateway": str(gateway.pk)})
        except PortAlreadyAllocatedError as err:
            print(f"Failed to launch Gateway. Port {err.port} is already taken.")
            exit(1)
        except Exception as err:
            print(f"Failed to launch Gateway: {err}")
            exit(1)

        print(f"Successfully launched Gateway {gateway.name}")

    def _add_via_ssh(self, gateway_ssh: str, database_name: str, ssh_port: str = "22", **kwargs):
        from fractal.gateway.models import Gateway
        from fractal_database.models import Database
        from fractal_database.replication.tasks import replicate_fixture

        try:
            database = Database.objects.get(name=database_name)
        except Database.DoesNotExist:
            print(f"Database {database_name} does not exist.")
            exit(1)

        try:
            result = sh.ssh(gateway_ssh, "-p", str(ssh_port), "fractal gateway export")
        except Exception as err:
            print(f"Failed to connect to Gateway:\n{err.stderr.decode()}")
            exit(1)

        print("Syncing Gateway into local database")
        gateway_fixture = json.loads(result.strip())
        for item in gateway_fixture:
            if item["model"] == "gateway.gateway":
                gateway_uuid = item["pk"]
                # FIXME: Gateway should not include any databases in its fixture
                # (dont want to leak potentially other groups, etc.)
                # item["fields"]["databases"] = []
                break
        else:
            # should never happen
            print("Gateway did not return a gateway fixture")
            exit(1)

        # check to see if the gateway has already been loaded once into the local database
        try:
            gateway = Gateway.objects.get(pk=gateway_uuid)
        except Gateway.DoesNotExist:
            asyncio.run(replicate_fixture(json.dumps(gateway_fixture)))
            gateway = Gateway.objects.get(pk=gateway_uuid)

        gateway.databases.add(database)
        gateway.ssh_config["host"] = gateway_ssh
        gateway.ssh_config["port"] = ssh_port
        gateway.save()
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
    def register(self, gateway_name: str, **kwargs):
        """
        Creates a dedicated account for the Gateway on the homeserver you
        are replicating to.
        ---
        Args:
            gateway_name: Name of the Gateway.
        """
        from fractal.gateway.models import Gateway
        from fractal_database.models import Database

        from homeserver.core.models import Group

        # attempt to fetch gateway and its ssh config
        try:
            gateway = Gateway.objects.get(name__icontains=gateway_name)
        except Gateway.DoesNotExist:
            print(f"Gateway {gateway_name} does not exist.")
            exit(1)

        if not gateway.ssh_config:
            print(
                f"Cannot register gateway: {gateway.name}. It does not have an SSH configuration."
            )
            exit(1)

        # fetch the primary target of the current database
        current_database = Database.current_db()
        origin_channel = current_database.origin_channel()
        if not origin_channel:
            print(
                f"Cannot register gateway. Your current database {current_database} is not being replicated anywhere."
            )
            exit(1)

        # create device credentials for each gateway device if it doesn't already exist
        for membership in gateway.device_memberships.all():
            device = membership.device
            device.add_membership(current_database)
            personal_space = Group.objects.get(name="Personal Space")
            device.add_membership(personal_space)

            membership.refresh_from_db()
            # serialize device credentials and load them into the gateway's database
            device_fixture = membership.to_fixture(json=True, with_relations=True)

            print(f"device fixture: {device_fixture}")

            try:
                result = sh.ssh(
                    gateway.ssh_config["host"],
                    "-p",
                    str(gateway.ssh_config["port"]),
                    "fractal db sync -",
                    _in=device_fixture,
                )
            except Exception as err:
                print(f"Failed to connect to Gateway:\n{err.stderr.decode()}")
                exit(1)

            # join device to current database and the personal space
            # join_device_to_database(
            #     current_database, current_database, [device.pk], action="post_add"
            # )
            # join_device_to_database(
            #     personal_space, personal_space, [device.pk], action="post_add"
            # )


Controller = FractalGatewayController

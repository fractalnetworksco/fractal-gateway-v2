import traceback

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
    def _init(self, **kwargs):
        from fractal.gateway.models import Gateway
        from fractal.gateway.signals import create_gateway_and_homeserver_for_current_db

        gateway_name = "fractal-gateway"
        try:
            Gateway.objects.get(name=gateway_name)
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
        launch_gateway(gateway_name, labels={"f.gateway": gateway.name})

        print(f"Successfully initialized and launched Gateway: {gateway_name}")

    @cli_method
    def init(self):
        """
        Initializes the current Device as a Gateway.
        ---
        """
        # attempt to fetch gateway. Exit if it already exists
        fdb_controller = FractalDatabaseController()
        fdb_controller.init(project_name="fractal_gateway", quiet=True, exist_ok=True)

        self._init()  # type: ignore

    @use_django
    @cli_method
    def launch(self, **kwargs):
        """
        Launches a Gateway.
        ---
        """
        from fractal.gateway.models import Gateway

        gateway = Gateway.objects.get(name="fractal-gateway")
        try:
            launch_gateway(gateway.name)
        except PortAlreadyAllocatedError as err:
            print(f"Failed to launch Gateway. Port {err.port} is already taken.")
            exit(1)
        except Exception as err:
            print(f"Failed to launch Gateway: {err}")
            exit(1)

        print(f"Successfully launched Gateway {gateway.name}")

    @use_django
    @cli_method
    def create(self, name: str, **kwargs):
        """
        Create a Gateway.
        ---
        Args:
            name: Name of the Gateway.
        """
        from fractal.gateway.models import Gateway

        g = Gateway.objects.create(name=name)
        print(f"Successfully created gateway: {g.name}")


Controller = FractalGatewayController

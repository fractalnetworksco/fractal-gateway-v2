from clicz import cli_method
from fractal.gateway.exceptions import PortAlreadyAllocatedError
from fractal.gateway.utils import (
    build_gateway_containers,
    check_port_availability,
    launch_gateway,
)
from fractal_database.utils import use_django


class FractalGatewayController:
    PLUGIN_NAME = "gateway"
    HTTP_GATEWAY_PORT = 80
    HTTPS_GATEWAY_PORT = 443

    @use_django
    @cli_method
    def list(self, **kwargs):
        """
        List Gateways.
        ---
        """
        from fractal.gateway.models import Gateway

        gateways = Gateway.objects.all()
        for gateway in gateways:
            print(f'"{gateway.name}"')

    @use_django
    @cli_method
    def init(self, **kwargs):
        """
        Initializes the current Device as a Gateway.
        ---
        """
        from fractal.gateway.models import Gateway
        from fractal.gateway.signals import create_gateway_and_homeserver_for_current_db
        from fractal_database.models import Device

        try:
            Device.current_device()
        except Device.DoesNotExist:
            print("No Device found. Please create a Device first.")
            exit(1)

        # attempt to fetch gateway. Exit if it already exists
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
        except Exception as err:
            print(f"Error initializing Gateway: {err}")
            exit(1)

        # launch docker container
        launch_gateway(gateway.name)

        print(f"Successfully initialized current Device as a Gateway")

    @use_django
    @cli_method
    def launch(self, **kwargs):
        """
        Launches a Gateway.
        ---
        """
        from fractal.gateway.models import Gateway

        gateway = Gateway.objects.get(name="Fractal-Gateway")
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

from clicz import cli_method
from fractal_database.utils import use_django


class FractalGatewayController:
    PLUGIN_NAME = "gateway"

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
        from fractal.gateway.signals import create_matrix_homeserver_for_default_target

        try:
            create_matrix_homeserver_for_default_target()
        except Exception as err:
            print(f"Error initializing Gateway: {err}")
            exit(1)

        print(f"Successfully initialized current Device as a Gateway")

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

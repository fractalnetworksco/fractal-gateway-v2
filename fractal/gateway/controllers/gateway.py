from fractal.cli import cli_method
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
            print(gateway.name)

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

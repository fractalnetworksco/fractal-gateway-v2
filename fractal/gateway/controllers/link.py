from typing import Optional

from clicz import cli_method
from fractal_database.utils import use_django


class FractalLinkController:
    PLUGIN_NAME = "link"
    HTTP_GATEWAY_PORT = 80
    HTTPS_GATEWAY_PORT = 443

    @use_django
    @cli_method
    def list(self, **kwargs):
        """
        List all Links.
        ---
        """
        from fractal.gateway.models import Link

        links = Link.objects.all()
        for link in links:
            print(f'"{link}"')

    @use_django
    @cli_method
    def create(self, fqdn: Optional[str] = None, **kwargs):
        """
        Create a link.
        ---
        """
        from fractal.gateway.models import Gateway, Link

        gateways = Gateway.objects.all()
        for gateway in gateways:
            print(f'"{gateway.name}"')


Controller = FractalLinkController

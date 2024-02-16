import asyncio
from sys import exit
from typing import Optional

from clicz import cli_method
from fractal.gateway.utils import get_gateway_container
from fractal_database.utils import use_django
from taskiq.kicker import AsyncKicker


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
        Create a link. The created link will be added to all gateways.
        ---
        Args:
            fqdn: Fully qualified domain name for the link (i.e. subdomain.mydomain.com).
        """
        from fractal.gateway.models import Gateway, Link

        gateways = Gateway.objects.all()
        if not gateways.exists():
            print(f"Error creating link: Could not find any gateways.")
            exit(1)

        link = Link.objects.create(fqdn=fqdn)
        link.gateways.add(*gateways)

        print(f"Successfully created link: {link}")
        print(
            f"Added link to the following gateways: {', '.join([str(gateway) for gateway in gateways])}"
        )

    @use_django
    @cli_method
    def up(self, link_fqdn: str, **kwargs):
        """
        Bring the link up.
        ---
        Args:
            link_fqdn: Fully qualified domain name for the link (i.e. subdomain.mydomain.com).
        """
        from fractal.gateway.tasks import link_up

        gateway = get_gateway_container()

        # get device name for gateway

        async def _link_up(link_fqdn):
            # link_up.kicker().with_labels({"queue": "device", "device": ""})
            task = await link_up.kiq(link_fqdn)
            return await task.wait_result()

        asyncio.run(link_up(link_fqdn))


Controller = FractalLinkController

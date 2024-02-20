import asyncio
from sys import exit
from typing import Optional

from clicz import cli_method
from fractal.gateway.utils import generate_link_compose_snippet, get_gateway_container
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
    def create(self, fqdn: str, **kwargs):
        """
        Create a link. The created link will be added to all gateways.
        TODO: Handle automatic subdomain creation. For now, requires that subdomain is passed
        ---
        Args:
            fqdn: Fully qualified domain name for the link (i.e. subdomain.mydomain.com).
        """
        from fractal.gateway.models import Gateway, Link

        gateways = Gateway.objects.all()
        if not gateways.exists():
            print("Error creating link: Could not find any gateways.")
            exit(1)

        link = Link.objects.create(fqdn=fqdn)
        link.gateways.add(*gateways)

        print(f"Successfully created link: {link}")
        print(
            f"Added link to the following gateways: {', '.join([str(gateway) for gateway in gateways])}"
        )

    @use_django
    @cli_method
    def up(self, link_fqdn: str, expose: str, **kwargs):
        """
        Bring the link up.
        ---
        Args:
            link_fqdn: Fully qualified domain name for the link (i.e. subdomain.mydomain.com).
            expose: hostname:port to expose the link on (i.e. nginx:80).
        """
        from fractal.gateway.models import Gateway, Link
        from fractal.gateway.tasks import link_up

        gateway = get_gateway_container()
        gateway_id = gateway.labels.get("f.gateway")

        try:
            gateway = Gateway.objects.get(name=gateway_id)
            _ = gateway.links.get(fqdn=link_fqdn)
        except Gateway.DoesNotExist:
            print(f"Error: Could not find gateway {gateway_id} in your local database")
            exit(1)
        except Link.DoesNotExist:
            print(
                f"Error: Could not find link with fqdn {link_fqdn} for gateway {gateway_id} in your local database"
            )
            exit(1)

        async def _link_up(link_fqdn: str):
            # link_up.kicker().with_labels({"queue": "device", "device": ""})
            task = await link_up.kiq(link_fqdn)
            return await task.wait_result()

        # will instead kick this with the func above ^^^^
        gateway_link_public_key, link_address, client_private_key = asyncio.run(
            link_up(link_fqdn)
        )
        link_config = {
            "gateway_link_public_key": gateway_link_public_key,
            "link_address": link_address,
            "client_private_key": client_private_key,
        }
        print("Add the following to your app's docker-compose.yml:")
        print(generate_link_compose_snippet(link_config, link_fqdn, expose))


Controller = FractalLinkController

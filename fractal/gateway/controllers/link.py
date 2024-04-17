import asyncio
from sys import exit
from typing import Optional

from clicz import cli_method
from fractal.cli.fmt import display_data
from fractal.gateway.utils import generate_link_compose_snippet, get_gateway_container
from fractal_database.utils import use_django
from taskiq.kicker import AsyncKicker


class FractalLinkController:
    PLUGIN_NAME = "link"
    HTTP_GATEWAY_PORT = 80
    HTTPS_GATEWAY_PORT = 443

    @use_django
    @cli_method
    def list(self, format: str = "table", **kwargs):
        """
        List all Links.
        ---
        Args:
            format: The format to display the data in. Options are "table" or "json". Defaults to "table".

        """
        from fractal.gateway.models import Link

        links = Link.objects.all()
        if not links.exists():
            print("No links found")
            exit(0)

        # TODO: Include health information when available (link is running)
        data = [
            {
                "fqdn": link.fqdn,
                "gateways": ", ".join([gateway.name for gateway in link.gateways.all()]),
            }
            for link in links
        ]

        display_data(data, title="Links", format=format)

    @use_django
    @cli_method
    def create(self, fqdn: str, gateway_name: str, **kwargs):
        """
        Create a link. The created link will be added to all gateway_names.
        TODO: Handle automatic subdomain creation. For now, requires that subdomain is passed
        ---
        Args:
            fqdn: Fully qualified domain name for the link (i.e. subdomain.mydomain.com).
            gateway_name: Name of the gateway to create link to.
        """
        from fractal.gateway.models import Gateway, Link

        gateway = Gateway.objects.filter(name__icontains=gateway_name)
        if not gateway.exists():
            print(f"Error creating link: Could not find gateway {gateway_name}.")
            exit(1)
        gateway = gateway.first()

        link = Link.objects.create(fqdn=fqdn)
        link.gateways.add(gateway)

        print(f"Successfully created link: {link}")
        print(f"Added link to the following gateway: {gateway.name}")
        return link

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
        print(generate_link_compose_snippet(link_config, link_fqdn, expose))


Controller = FractalLinkController

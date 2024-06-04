import asyncio
import sys
from sys import exit
from typing import TYPE_CHECKING, Optional

from clicz import cli_method
from fractal.cli.fmt import display_data
from fractal.gateway.utils import generate_link_compose_snippet, get_gateway_container
from fractal_database import ssh
from fractal_database.utils import use_django
from taskiq.kicker import AsyncKicker

if TYPE_CHECKING:
    from fractal.gateway.models import Gateway


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
    def create(
        self, fqdn: str, gateway_name: str, output_as_json=False, override: bool = False, **kwargs
    ):
        """
        Create a link. The created link will be added to all gateway_names.
        TODO: Handle automatic subdomain creation. For now, requires that subdomain is passed
        ---
        Args:
            fqdn: Fully qualified domain name for the link (i.e. subdomain.mydomain.com).
            gateway_name: Name of the gateway to create link to.
            output_as_json: Whether to output the link as a JSON fixture. Defaults to False.
            override: Whether to override the link if it already exists. Defaults to False.
        """
        from fractal.gateway.models import Gateway, Link

        gateway = Gateway.objects.filter(name__icontains=gateway_name)
        if not gateway.exists():
            print(f"Error creating link: Could not find gateway {gateway_name}.", file=sys.stderr)
            exit(1)
        gateway = gateway.first()

        try:
            link = Link.objects.get(fqdn=fqdn)
            if not override:
                print(
                    f"Error creating link: Link {fqdn} already exists. Specify --override to forcefully override.",
                    file=sys.stderr,
                )
                exit(1)
        except Link.DoesNotExist:
            try:
                link = Link.objects.create(fqdn=fqdn)
            except Exception as err:
                print(
                    f"Error creating link: Could not create link {fqdn}: {err}", file=sys.stderr
                )
                exit(1)

        link.gateways.add(gateway)

        if output_as_json:
            print(link.to_fixture(json=True))
        else:
            print(f"Successfully created link: {link}")
            print(f"Added link to the following gateway: {gateway.name}")
        return link

    @use_django
    def up_over_ssh(self, gateway: "Gateway", link_fqdn: str, **kwargs):
        host = gateway.ssh_config["host"]
        port = gateway.ssh_config["port"]

        try:
            result = ssh(host, port, f"fractal link up {link_fqdn}")
        except Exception as err:
            print(f"Error: Could not bring link {link_fqdn} up: {err}", file=sys.stderr)
            exit(1)

        return result.strip().split(",")

    @use_django
    @cli_method
    def up(self, link_fqdn: str, **kwargs):
        """
        Bring the link up.
        ---
        Args:
            link_fqdn: Fully qualified domain name for the link (i.e. subdomain.mydomain.com).
        """
        from fractal.gateway.models import Gateway, Link
        from fractal.gateway.tasks import link_up
        from fractal.gateway.utils import build_gateway_containers

        build_gateway_containers()

        gateway = get_gateway_container()
        gateway_id = gateway.labels.get("f.gateway")

        try:
            gateway = Gateway.objects.get(pk=gateway_id)
            _ = gateway.links.get(fqdn=link_fqdn)
        except Gateway.DoesNotExist:
            print(
                f"Error: Could not find gateway {gateway_id} in your local database",
                file=sys.stderr,
            )
            exit(1)
        except Link.DoesNotExist:
            print(
                f"Error: Could not find link with fqdn {link_fqdn} for gateway {gateway_id} in your local database",
                file=sys.stderr,
            )
            exit(1)

        async def _link_up(link_fqdn: str, room_id: str):
            # link_up.kicker().with_labels({"queue": "device", "device": ""})
            task = await link_up.kiq(link_fqdn)
            return await task.wait_result()

        # if gateway.ssh_config:
        #     gateway_link_public_key, link_address, client_private_key = self.up_over_ssh(
        #         gateway, link_fqdn
        #     )
        # else:
        # will instead kick this with the func above ^^^^
        gateway_link_public_key, link_address, client_private_key = asyncio.run(
            link_up(link_fqdn)
        )
        link_config = {
            "gateway_link_public_key": gateway_link_public_key,
            "link_address": link_address,
            "client_private_key": client_private_key,
        }
        print(",".join(link_config.values()))


Controller = FractalLinkController

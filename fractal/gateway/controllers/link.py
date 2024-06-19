import asyncio
import sys
from sys import exit
from typing import TYPE_CHECKING

import tldextract
from clicz import cli_method
from fractal.cli.fmt import display_data
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
                "fqdn": link.domain,
                "gateways": ", ".join([gateway.name for gateway in link.gateways.all()]),
            }
            for link in links
        ]

        display_data(data, title="Links", format=format)

    @use_django
    @cli_method
    def create(
        self, fqdn: str, gateway_id: str, output_as_json=False, force: bool = False, **kwargs
    ):
        """
        Create a link. The created link will be added to all gateway_names.
        TODO: Handle automatic subdomain creation. For now, requires that subdomain is passed
        ---
        Args:
            fqdn: Fully qualified domain name for the link (i.e. subdomain.mydomain.com).
            gateway_id: ID of the gateway to create link to.
            output_as_json: Whether to output the link as a JSON fixture. Defaults to False.
            force: Whether to continue if the link already exists. Defaults to False.
        """
        from fractal.gateway.models import Gateway, Link

        gateway = Gateway.objects.filter(pk=gateway_id)
        if not gateway.exists():
            print(
                f"Error creating link: Could not find gateway by the id of {gateway_id}.",
                file=sys.stderr,
            )
            exit(1)
        gateway = gateway.first()

        with gateway.as_current_database():
            url = tldextract.extract(fqdn)
            domain = url.registered_domain or url.domain
            subdomain = url.subdomain

            try:
                domain = gateway.get_domain(domain=domain)
            except Exception as err:
                print(
                    f"Error creating link: Could not find fqdn {domain} for gateway {gateway}: {err}",
                    file=sys.stderr,
                )
                exit(1)

            try:
                link = Link.objects.get(domain=domain, subdomain=subdomain)
                if not force:
                    print(
                        f"Error creating link: Link {domain} already exists. Specify --override to forcefully override.",
                        file=sys.stderr,
                    )
                    exit(1)
            except Link.DoesNotExist:
                try:
                    link = Link.objects.create(domain=domain, subdomain=subdomain)
                except Exception as err:
                    print(
                        f"Error creating link: Could not create link {domain}: {err}",
                        file=sys.stderr,
                    )
                    exit(1)

            if output_as_json:
                print(link.to_fixture(json=True))
            else:
                print(f"Successfully created link: {link}")
                print(f"Added link to the following gateway: {gateway.name}")
            return link

    @use_django
    @cli_method
    def up(self, gateway_id: str, link_fqdn: str, **kwargs):
        """
        Bring the link up.
        ---
        Args:
            gateway_id: ID of the gateway service.
            link_fqdn: Fully qualified domain name for the link (i.e. subdomain.mydomain.com).
        """
        from fractal.gateway.models import Domain, Gateway, Link
        from fractal.gateway.tasks import link_up
        from fractal.gateway.utils import build_gateway_containers

        build_gateway_containers()

        try:
            gateway = Gateway.objects.get(pk=gateway_id)
        except Gateway.DoesNotExist:
            print(
                f"Error: Could not find gateway {gateway_id} in your local database",
                file=sys.stderr,
            )
            exit(1)

        url = tldextract.extract(link_fqdn)
        domain = url.registered_domain or url.domain
        subdomain = url.subdomain

        try:
            domain = gateway.get_domain(domain=domain)
        except Domain.DoesNotExist:
            print(
                f"Error: Could not find domain for {domain} for gateway {gateway.name} ({str(gateway.id)}) in your local database",
                file=sys.stderr,
            )
            exit(1)

        try:
            Link.objects.get(domain=domain, subdomain=subdomain)
        except Link.DoesNotExist:
            print(
                f"Error: Could not find link {link_fqdn} in your local database",
                file=sys.stderr,
            )
            exit(1)

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

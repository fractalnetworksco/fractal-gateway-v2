import docker
from asgiref.sync import sync_to_async
from fractal.gateway.exceptions import GatewayContainerNotFound
from fractal.gateway.models import Gateway
from fractal.gateway.utils import (
    generate_wireguard_keypair,
    get_gateway_container,
    launch_link,
)
from fractal_database_matrix.broker import broker


@broker.task()
async def link_up(link_fqdn: str):
    """ """
    print("Running link up task")
    client = docker.from_env()
    gateway = await Gateway.objects.aget(name="fractal-gateway")

    gateway_container = await sync_to_async(get_gateway_container)(
        name=gateway.name, client=client
    )
    if not gateway_container:
        raise GatewayContainerNotFound(gateway.name)

    link_private_key, link_public_key = generate_wireguard_keypair(client)

    gateway_private_key = launch_link(link_fqdn, link_public_key, client=client)

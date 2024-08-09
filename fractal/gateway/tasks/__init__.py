from typing import Optional

import docker
from asgiref.sync import sync_to_async
from fractal.gateway.utils import (
    generate_wireguard_keypair,
    get_gateway_container,
    launch_link,
)
from fractal_database_matrix.broker.instance import broker


@broker.task(queue="device")
async def link_up(
    link_fqdn: str,
    tcp_forwarding: bool,
    forward_port: Optional[str] = None,
) -> tuple[str, str, str, str]:
    """
    Device task intended to be run by a device running next to a Gateway container (Gateway Device)
    Handles launching a link container and adding it to the gateway network.
    On success, returns all of the necessary configuration for the client to connect to the link.

    Returns:
    - tuple[
        wireguard_pubkey,
        link_address,
        client_private_key,
        forward_port,
    ], contains the generated WireGuard public key, the link's address, the client's private key, and the forward_port that was assigned.
    """
    client = docker.from_env()

    # ensure that the gateway container exists
    await sync_to_async(get_gateway_container)(client=client)

    # generate link client keypair
    client_private_key, client_public_key = generate_wireguard_keypair(client)

    gateway_link_public_key, link_address, forward_port = launch_link(
        link_fqdn,
        client_public_key,
        client=client,
        tcp_forwarding=tcp_forwarding,
        forward_port=forward_port,
    )
    return (gateway_link_public_key, link_address, client_private_key, forward_port)

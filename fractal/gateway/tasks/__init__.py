import docker
import sh
from asgiref.sync import sync_to_async
from fractal.gateway.utils import (
    generate_wireguard_keypair,
    get_gateway_container,
    launch_link,
)
from fractal_database_matrix.broker import broker


@broker.task(queue="device")
async def link_up(link_fqdn: str) -> tuple[str, str, str]:
    """
    Device task intended to be run by a device running next to a Gateway container (Gateway Device)
    Handles launching a link container and adding it to the gateway network.
    On success, returns all of the necessary configuration for the client to connect to the link.

    Returns:
    - tuple[
        wireguard_pubkey,
        link_address,
        client_private_key
    ], contains the generated WireGuard public key, the link's address, and the client's private key.
    """
    client = docker.from_env()

    # ensure that the gateway container exists
    await sync_to_async(get_gateway_container)(client=client)

    # generate link client keypair
    client_private_key, client_public_key = generate_wireguard_keypair(client)

    gateway_link_public_key, link_address = launch_link(
        link_fqdn, client_public_key, client=client
    )
    return (gateway_link_public_key, link_address, client_private_key)


def link_up_ssh(ssh_config: dict, link_fqdn: str) -> str:
    """
    Launches a link container with the specified FQDN and public key using SSH.
    """
    try:
        result = sh.ssh(
            ssh_config["host"], "-p", ssh_config["port"], "fractal link up", link_fqdn
        ).strip()
    except Exception as err:
        print(f"Failed to connect to Gateway:\n{err.stderr.decode()}")
        exit(1)

    return result.split(",")

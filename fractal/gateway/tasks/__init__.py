import logging
from typing import Optional

import docker
from asgiref.sync import sync_to_async
from fractal.gateway.utils import (
    generate_wireguard_keypair,
    get_gateway_container,
    launch_link,
)
from fractal_database.utils import use_django
from fractal_database_matrix.broker.instance import broker
from taskiq import Context, TaskiqDepends

logger = logging.getLogger(__name__)


@use_django
async def _verify_matrix_id_is_database_member(matrix_id: str, link_fqdn: str, **kwargs):
    from fractal.gateway.models import Link
    from fractal_database.models import DatabaseMembership

    logger.info(
        "Verifying that %s is a user of the database %s belongs to" % (matrix_id, link_fqdn)
    )

    # fetch the link and the database it belongs to
    try:
        link = await Link.aget_by_url(
            link_fqdn, select_related=["service_config", "service_config__service"]
        )
    except Link.DoesNotExist:
        raise ValueError(f"Link {link_fqdn} not found")

    # verify that the matrix id is a member of the database
    try:
        database = link.service_config.service
        await DatabaseMembership.objects.select_related("user").aget(
            user__matrix_id=matrix_id, database=database
        )
    except DatabaseMembership.DoesNotExist:
        raise Exception(
            f"Cannot link up as the kicker is not a member of the database: {database}"
        )

    return True


@broker.task(queue="device")
async def link_up(
    link_fqdn: str,
    tcp_forwarding: bool,
    forward_port: Optional[str] = None,
    context: Context = TaskiqDepends(),  # needed to get the task kicker
) -> tuple[str, str, str, str]:
    """
    Device task intended to be run by a device running next to a Gateway container (Gateway Device)
    If kicked via matrix, will check if the kicker matrix id is a member of the database the link fqdn
    belongs to. If so, the task handles launching a link container and adding it to the gateway network.

    On success, returns all of the necessary configuration for the client to connect to the link.

    Returns:
    - tuple[
        wireguard_pubkey,
        link_address,
        client_private_key,
        forward_port,
    ], contains the generated WireGuard public key, the link's address, the client's private key, and the forward_port that was assigned.
    """
    # get the user from the kicked message labels
    # context will have a message attr if the task was yielded from a worker
    if hasattr(context, "message"):
        matrix_id = context.message.labels.get("sender")

        try:
            await _verify_matrix_id_is_database_member(matrix_id, link_fqdn)
        except Exception as e:
            raise ValueError(f"Error verifying matrix id {matrix_id} is database member: {e}")

    else:
        # FIXME: task was called directly, not from matrix
        logger.warning("FIXME: task was called directly, not from matrix. Can't get matrix_id")

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

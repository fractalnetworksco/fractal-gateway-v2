import logging
from typing import TYPE_CHECKING

from django.db.models.signals import post_save
from django.dispatch import receiver
from fractal.gateway.models import Gateway, Link

if TYPE_CHECKING:
    from fractal_database_matrix.models import MatrixReplicationTarget

logger = logging.getLogger("django")


def create_gateway_and_homeserver_for_current_db(gateway_name: str, *args, **kwargs) -> Gateway:
    """
    Creates a Gateway and a MatrixHomeserver for the current database's primary
    ReplicationTarget.
    """
    from fractal.gateway.models import Gateway, MatrixHomeserver
    from fractal_database.models import Database

    logger.info("In create_matrix_homeserver_for_default_target signal handler")

    database = Database.current_db()
    primary_target: "MatrixReplicationTarget" = database.primary_target()  # type: ignore
    homeserver_url = primary_target.homeserver

    gateway = database.gateways.all()  # type: ignore
    if not gateway.exists():  # type: ignore
        logger.info(f"Creating gateway for primary database")
        gateway = Gateway.objects.create(name=gateway_name)
        gateway.databases.add(database)
    else:
        gateway = gateway[0]

    # get the lowest priority homeserver for the current database
    homeserver = database.gateways.filter(homeservers__url=homeserver_url).order_by(
        "homeservers__priority"
    )
    if homeserver.exists():
        logger.info(f"MatrixHomeserver for {homeserver_url} already exists not creating")
    else:
        MatrixHomeserver.objects.create(
            gateway=gateway, url=homeserver_url, database=database, priority=0
        )
        logger.info(f"Created MatrixHomeserver for {homeserver_url}")

    return gateway


# @receiver(post_save, sender=Link)
# def create_link(
#     sender: "Link",
#     instance: "Link",
#     created: bool,
#     raw: bool,
#     **kwargs,
# ):
#     """FIXME"""
#     if raw:
#         logger.info("Skipping create link signal handler for fixture load")
#         return

#     generate_link_compose_snippet(instance.fqdn)

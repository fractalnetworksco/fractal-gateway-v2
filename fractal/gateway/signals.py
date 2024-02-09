import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver
from fractal.gateway.models import Domain, Gateway, Link

if TYPE_CHECKING:
    from fractal_database_matrix.models import MatrixReplicationTarget

logger = logging.getLogger("django")


def create_matrix_homeserver_for_default_target(*args, **kwargs) -> None:
    """
    Ensures that a MatrixHomeserver is created
    for the configured Database's MatrixReplicationTarget
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
        gateway = Gateway.objects.create(name=f"{database.name.capitalize()} Gateway")
        gateway.databases.add(database)
    else:
        gateway = gateway[0]

    # get the lowest priority homeserver for the current database

    homeserver = database.gateways.filter(homeservers__url=homeserver_url).order_by(
        "homeservers__priority"
    )
    if homeserver.exists():
        logger.info(f"MatrixHomeserver for {homeserver_url} already exists not creating")
        return
    else:
        MatrixHomeserver.objects.create(
            gateway=gateway, url=homeserver_url, database=database, priority=0
        )
        logger.info(f"Created MatrixHomeserver for {homeserver_url}")


@receiver(post_save, sender=Gateway)
def create_gateway_wireguard_network(
    sender: "Gateway",
    instance: "Gateway",
    created: bool,
    raw: bool,
    **kwargs,
):
    """FIXME"""
    print(f"running create_gateway_wireguard_network for {instance}")


@receiver(post_save, sender=Link)
def create_link_wireguard(
    sender: "Link",
    instance: "Link",
    created: bool,
    raw: bool,
    **kwargs,
):
    """FIXME"""
    print(f"running create_link_wireguard for {instance}")


@receiver(m2m_changed, sender=Gateway.databases.through)
@receiver(m2m_changed, sender=Domain.gateways.through)
def replicate_domain_after_m2m_changed(
    sender: "Domain.gateways.through",
    instance: "Domain",
    action: str,
    reverse: bool,
    model: "Gateway",
    pk_set: set,
    **kwargs,
):
    """
    Ensures that the Gateway or Domain is replicated if their
    respective m2m relationships have changed.
    """
    instance.schedule_replication()

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fractal_database_matrix.models import MatrixReplicationTarget

logger = logging.getLogger("djagno")


def create_matrix_homeserver_for_default_target(*args, **kwargs) -> None:
    """
    Post migration signal that ensures that a MatrixHomeserver is created
    for the configured Database's MatrixReplicationTarget
    """
    from fractal.gateway.models import Gateway, MatrixHomeserver
    from fractal_database.models import Database

    logger.info("In create_matrix_homeserver_for_default_target signal handler")

    database = Database.current_db()
    primary_target: "MatrixReplicationTarget" = database.primary_target()  # type: ignore
    homeserver_url = primary_target.homeserver

    gateway = database.gateway_set.all()  # type: ignore
    if not gateway.exists():  # type: ignore
        logger.info(f"Creating gateway for primary database")
        gateway = Gateway.objects.create(
            name=f"{database.name.capitalize()} Gateway", database=database
        )
    else:
        gateway = gateway[0]

    # get the lowest priority homeserver for the current database
    homeservers = MatrixHomeserver.objects.filter(
        gateway=gateway, url=homeserver_url, database=database
    ).order_by("priority")
    if homeservers.exists():
        logger.info(f"MatrixHomeserver for {homeserver_url} already exists not creating")
        return
    else:
        MatrixHomeserver.objects.create(
            gateway=gateway, url=homeserver_url, database=database, priority=0
        )
        logger.info(f"Created MatrixHomeserver for {homeserver_url}")

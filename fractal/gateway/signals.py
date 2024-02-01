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

    gateway = database.gateway_set.filter(primary=True)  # type: ignore
    if not gateway.exists():  # type: ignore
        logger.info(f"Creating gateway for primary database")
        gateway = Gateway.objects.create(
            name=f"{database.name.capitalize()} Primary Gateway", database=database, primary=True
        )
    else:
        gateway = gateway[0]

    homeserver, created = MatrixHomeserver.objects.get_or_create(
        gateway=gateway,
        url=homeserver_url,
        defaults={"url": homeserver_url, "name": primary_target.name},
    )

    if created:
        logger.info(f"Created MatrixHomeserver for {homeserver_url}")
    else:
        logger.info(f"MatrixHomeserver for {homeserver_url} already exists not creating")

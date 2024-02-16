import logging
from secrets import token_hex
from typing import TYPE_CHECKING

from django.db import transaction
from fractal.gateway.models import Gateway
from fractal_database.models import ReplicatedInstanceConfig

if TYPE_CHECKING:
    from fractal_database_matrix.models import MatrixReplicationTarget

logger = logging.getLogger("django")


def create_gateway_and_homeserver_for_current_db(gateway_name: str, *args, **kwargs) -> Gateway:
    """
    Creates a Gateway and a MatrixHomeserver for the current database's primary
    ReplicationTarget.
    """
    from fractal.gateway.models import Gateway, MatrixHomeserver
    from fractal_database.models import AppCatalog, Database, Device
    from fractal_database_matrix.models import MatrixReplicationTarget

    if not transaction.get_connection().in_atomic_block:
        with transaction.atomic():
            return create_gateway_and_homeserver_for_current_db(gateway_name, *args, **kwargs)

    logger.info("In create_matrix_homeserver_for_default_target signal handler")

    database = Database.current_db()
    primary_target: "MatrixReplicationTarget" = database.primary_target()  # type: ignore
    homeserver_url = primary_target.homeserver
    current_device = Device.current_device()
    try:
        fractal_catalog = AppCatalog.objects.get(name="fractal")
    except AppCatalog.DoesNotExist:
        raise Exception("Fractal AppCatalog not found")

    gateway = database.gateways.all()  # type: ignore

    # FIXME: should name should indicate who owns the gateway?
    gateway_name = f"{gateway_name}-{token_hex(4)}"
    if not gateway.exists():  # type: ignore
        logger.info("Creating gateway for primary database")

        gateway = Gateway.objects.create(
            name=gateway_name, app_instance_id=gateway_name, metadata=fractal_catalog
        )
        gateway.databases.add(database)
        gateway.devices.add(current_device)
    else:
        gateway = gateway[0]

    # create a representation for the Gateway
    gateway_target = MatrixReplicationTarget.objects.create(
        name=gateway_name,
        homeserver=homeserver_url,
        registration_token=primary_target.registration_token,
    )
    device_creds = primary_target.matrixcredentials_set.get(device=current_device)
    gateway_target.matrixcredentials_set.add(device_creds)

    instance_config = ReplicatedInstanceConfig.objects.create(instance=gateway)
    gateway_target.instances.add(instance_config)
    gateway.schedule_replication()

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

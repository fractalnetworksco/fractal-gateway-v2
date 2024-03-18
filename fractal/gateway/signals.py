import logging
from secrets import token_hex
from typing import TYPE_CHECKING

from django.db import transaction
from fractal.gateway.models import Gateway
from fractal_database.models import ReplicatedInstanceConfig

if TYPE_CHECKING:
    from fractal_database_matrix.models import MatrixReplicationTarget

logger = logging.getLogger(__name__)


def create_gateway_and_homeserver_for_current_db(gateway_name: str, *args, **kwargs) -> Gateway:
    """
    Creates a Gateway and a MatrixHomeserver for the current database's primary
    ReplicationTarget.
    """
    from fractal.gateway.models import (
        Gateway,
        GatewayReplicationTarget,
        MatrixHomeserver,
    )
    from fractal_database.models import AppCatalog, Database, Device

    if not transaction.get_connection().in_atomic_block:
        with transaction.atomic():
            return create_gateway_and_homeserver_for_current_db(gateway_name, *args, **kwargs)

    database = Database.current_db()
    primary_target: "MatrixReplicationTarget" = database.primary_target()  # type: ignore
    homeserver_url = primary_target.homeserver
    current_device = Device.current_device()
    try:
        fractal_catalog = AppCatalog.objects.get(name="fractal")
    except AppCatalog.DoesNotExist:
        raise Exception("Fractal AppCatalog not found")

    gateway = database.gateways.all()  # type: ignore

    # FIXME: should name indicate who owns the gateway?
    gateway_name = f"{gateway_name}-{token_hex(4)}"
    if not gateway.exists():  # type: ignore
        logger.info("Creating gateway %s for database %s" % (gateway_name, database))

        gateway = Gateway.objects.create(
            name=gateway_name,
            app_instance_id=gateway_name,
            metadata=fractal_catalog,
            database=database,
        )
        logger.info("Adding gateway %s to current database %s" % (gateway, database))
        gateway.databases.add(database)
        logger.info("Adding current device %s to gateway %s" % (current_device, gateway))
        gateway.devices.add(current_device)
    else:
        gateway = gateway[0]

    # create a representation for the Gateway
    try:
        gateway_target = GatewayReplicationTarget.objects.get(
            name=gateway_name,
            homeserver=homeserver_url,
            registration_token=primary_target.registration_token,
        )
        logger.info("GatewayReplicationTarget for %s already exists" % gateway_name)
        return gateway
    except GatewayReplicationTarget.DoesNotExist:
        pass

    logger.info("Creating GatewayReplicationTarget for %s" % gateway_name)
    gateway_target = GatewayReplicationTarget.objects.create(
        name=gateway_name,
        homeserver=homeserver_url,
        registration_token=primary_target.registration_token,
    )

    # get matrix creds for the current device from the primary target
    device_creds = primary_target.matrixcredentials_set.get(device=current_device)
    logger.info(
        "Adding current device (%s) MatrixCredentials to the created GatewayReplicationTarget"
        % current_device
    )
    gateway_target.matrixcredentials_set.add(device_creds)
    gateway_target.add_instance(gateway)

    # get the lowest priority homeserver for the current database
    homeserver = database.gateways.filter(homeservers__url=homeserver_url).order_by(
        "homeservers__priority"
    )
    if homeserver.exists():
        logger.warning("MatrixHomeserver for %s already exists. Not creating" % homeserver_url)
    else:
        MatrixHomeserver.objects.create(
            gateway=gateway, url=homeserver_url, database=database, priority=0
        )
        logger.info("Successfully created MatrixHomeserver for %s" % homeserver_url)

    return gateway

import logging
from secrets import token_hex

from django.db import transaction
from fractal.gateway.models import Gateway
from fractal_database.models import Database, Device

logger = logging.getLogger(__name__)


def create_gateway_and_homeserver_for_current_db(
    gateway_name: str, fqdn: str, *args, **kwargs
) -> Gateway:
    """
    Creates a Gateway and a MatrixHomeserver for the current database's origin
    ReplicationChannel.
    """
    if not transaction.get_connection().in_atomic_block:
        with transaction.atomic():
            return create_gateway_and_homeserver_for_current_db(
                gateway_name, fqdn, *args, **kwargs
            )

    from fractal.gateway.models import Domain, Gateway
    from fractal_database.models import ServiceInstanceConfig

    current_database = Database.current_db()
    current_device = Device.current_device()

    gateway = current_database.gateways.filter(name__icontains=gateway_name).first()  # type: ignore

    # FIXME: should name indicate who owns the gateway?
    if not gateway:
        logger.info("Creating gateway %s for database %s" % (gateway_name, current_database))
        gateway = Gateway.objects.create(name=f"{gateway_name}-{token_hex(4)}")
        logger.info("Adding gateway %s to current database %s" % (gateway, current_database))
        gateway.databases.add(current_database)
        logger.info("Adding current device %s to gateway %s" % (current_device, gateway))
        current_device.add_membership(gateway)

        for user in current_database.users:
            logger.info("Adding current database member %s to gateway %s" % (user, gateway))
            user.add_membership(gateway)

    # add the fqdn to the gateway's device
    gateway_fqdn, _ = Domain.objects.get_or_create(uri=fqdn)
    gateway_fqdn.devices.add(current_device)

    ServiceInstanceConfig.objects.create(
        service=gateway,
        current_device=current_device,
        target_state="running",
    )

    return gateway

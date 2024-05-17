import logging
from secrets import token_hex
from typing import TYPE_CHECKING

from django.db import transaction
from fractal.gateway.models import Gateway
from fractal_database.models import Database, Device

if TYPE_CHECKING:
    from fractal_database_matrix.models import MatrixReplicationChannel

logger = logging.getLogger(__name__)


def create_gateway_and_homeserver_for_current_db(gateway_name: str, *args, **kwargs) -> Gateway:
    """
    Creates a Gateway and a MatrixHomeserver for the current database's origin
    ReplicationChannel.
    """
    # from fractal.gateway.models import Gateway, MatrixHomeserver
    # from fractal_database_matrix.models import MatrixReplicationChannel

    # if not transaction.get_connection().in_atomic_block:
    #     with transaction.atomic():
    #         return create_gateway_and_homeserver_for_current_db(gateway_name, *args, **kwargs)

    # current_database = Database.current_db()
    # current_device = Device.current_device()

    # gateway = current_database.gateways.filter(name__icontains=gateway_name)  # type: ignore

    # # FIXME: should name indicate who owns the gateway?
    # gateway_name = f"{gateway_name}-{token_hex(4)}"
    # if not gateway.exists():  # type: ignore
    #     logger.info("Creating gateway %s for database %s" % (gateway_name, current_database))

    #     gateway = Gateway.objects.create(name=gateway_name)
    #     logger.info("Adding gateway %s to current database %s" % (gateway, current_database))
    #     gateway.databases.add(current_database)
    #     logger.info("Adding current device %s to gateway %s" % (current_device, gateway))
    #     current_device.add_membership(gateway)
    # else:
    #     gateway = gateway[0]

    # # create a representation for the Gateway
    # current_db_origin_channel: "MatrixReplicationChannel" = current_database.origin_channel()  # type: ignore
    # if not current_db_origin_channel:
    #     logger.warning(
    #         "Database %s does not have an origin replication channel. Gateway will not attempt to create its representation"
    #         % current_database
    #     )
    #     return gateway

    # homeserver_url = current_db_origin_channel.homeserver
    # try:
    #     MatrixReplicationChannel.objects.get(
    #         name=gateway_name,
    #         homeserver=homeserver_url,
    #         registration_token=current_db_origin_channel.registration_token,
    #     )
    #     logger.info("MatrixReplicationChannel for %s already exists" % gateway_name)
    #     return gateway
    # except MatrixReplicationChannel.DoesNotExist:
    #     pass

    # logger.info("Creating MatrixReplicationChannel for %s" % gateway_name)
    # gateway.create_channel(
    #     MatrixReplicationChannel,
    #     homeserver=homeserver_url,
    #     registration_token=current_db_origin_channel.registration_token,
    # )

    # # get the lowest priority homeserver for the current database
    # homeserver = current_database.gateways.filter(homeservers__url=homeserver_url).order_by(
    #     "homeservers__priority"
    # )
    # if homeserver.exists():
    #     logger.warning("MatrixHomeserver for %s already exists. Not creating" % homeserver_url)
    # else:
    #     MatrixHomeserver.objects.create(
    #         gateway=gateway, url=homeserver_url, database=current_database, priority=0
    #     )
    #     logger.info("Successfully created MatrixHomeserver for %s" % homeserver_url)

    # return gateway

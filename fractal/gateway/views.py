import logging
from typing import Optional

import requests
from django.db.models.query import QuerySet
from fractal.gateway.models import Gateway
from fractal_database.models import Database
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

# temporary
logger = logging.getLogger("django")
# logger = logging.getLogger(__name__)

WELL_KNOWN_ENDPOINT = ".well-known/matrix/client"


class WellKnownView(APIView):
    def _get_well_known(self, homeserver_url: str) -> Optional[str]:
        """
        FIXME: this is blocking for now
        """
        logger.info(f"Making request to {homeserver_url}")
        try:
            resp = requests.get(f"{homeserver_url}/{WELL_KNOWN_ENDPOINT}")
            if resp.ok:
                return resp.json()["m.homeserver"]["base_url"]
        except:
            return None

    def get(self, request):
        """
        Returns the first available well-known from the configured homeservers
        for the current Database's primary Gateway.

        If no well-known is found, 404 is returned.
        """
        current_db = Database.current_db()
        gateway = current_db.gateway_set.filter(primary=True)  # type: ignore
        if not gateway.exists():  # type: ignore
            return Response({}, status=status.HTTP_404_NOT_FOUND)

        gateway: Gateway = gateway[0]  # type: ignore
        homeserver = gateway.primary_homeserver(current_db)

        # make request to the current Gateway's primary homeserver
        base_url = self._get_well_known(homeserver.url)

        # if the primary homeserver is unavailable, attempt to find a well-known
        # from all other configured homeservres on the gateway
        if not base_url:
            logger.info(f"Primary homeserver {homeserver.url} is unavailable")
            homeservers = gateway.matrixhomeserver_set.exclude(url=homeserver.url)
            for homeserver in homeservers:
                base_url = self._get_well_known(homeserver.url)
                if base_url:
                    break

            if not base_url:
                return Response({}, status=status.HTTP_404_NOT_FOUND)

        return Response(
            {
                "m.homeserver": {"base_url": base_url},
            },
            status=status.HTTP_200_OK,
        )

import logging
from typing import Optional

import requests
from fractal_database_matrix.models import MatrixHomeserver
from rest_framework import status
from rest_framework.request import Request
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

    def get(self, request: Request):
        """
        Returns the first available well-known from the configured homeservers
        for the current Database's primary Gateway.

        If no well-known is found, 404 is returned.
        """
        # get the hostname from the request
        hostname = request.get_host().split(":")[0]
        homeservers = MatrixHomeserver.objects.filter(url__contains=hostname).order_by("priority")
        if not homeservers.exists():
            return Response(
                {"err": f"Homeserver {hostname} not found"}, status=status.HTTP_404_NOT_FOUND
            )
        primary_homeserver = homeservers[0]
        homeserver_priority = primary_homeserver.priority

        # which homeserver to use? use the host in the request then find
        # make request to the current Gateway's primary homeserver
        base_url = self._get_well_known(primary_homeserver.url)

        # if the primary homeserver is unavailable, attempt to find a well-known
        # from all other configured homeservres on the gateway
        if not base_url:
            logger.info(f"Primary homeserver {primary_homeserver.url} is unavailable")

            homeservers = homeservers.exclude(url=primary_homeserver.url)
            for homeserver in homeservers:
                base_url = self._get_well_known(homeserver.url)
                if base_url:
                    homeserver_priority = homeserver.priority
                    break

            if not base_url:
                return Response({}, status=status.HTTP_404_NOT_FOUND)

        return Response(
            {
                "m.homeserver": {"base_url": base_url},
                "f.homeserver.priority": homeserver_priority,
            },
            status=status.HTTP_200_OK,
        )

import os
import re

import docker
from docker.errors import APIError, NotFound
from docker.models.containers import Container
from docker.models.networks import Network
from fractal.gateway.exceptions import PortAlreadyAllocatedError

GATEWAY_DOCKERFILE_PATH = "gateway"
GATEWAY_IMAGE_TAG = "fractal-gateway:latest"
LINK_DOCKERFILE_PATH = "gateway-link"
LINK_IMAGE_TAG = "fractal-gateway-link:latest"


def check_port_availability(port: int) -> None:
    """
    Attempts to connect to a given port on the specified host to infer if the port is in use.

    Parameters:
    - host: String, the hostname or IP address to check the port on. Use 'localhost' or '127.0.0.1' for local checks.
    - port: Integer, the port number to check.

    Returns:
    - True if a connection to the port is successful (indicating something is listening on the port), False otherwise.
    """
    client = docker.from_env()

    try:
        client.containers.run("alpine:latest", ports={port: port}, remove=True)
    except APIError as err:
        port_number = get_port_from_error(err.explanation)  # type: ignore
        if port_number:
            raise PortAlreadyAllocatedError(port_number)
        else:
            raise err


def get_gateway_resource_path(file: str) -> str:
    import fractal.gateway

    path = os.path.join(os.path.dirname(fractal.gateway.__file__), "resources", file)
    # verify path exists
    if not os.path.exists(path):
        raise FileNotFoundError(f"Resource {file} not found")
    return path


def build_gateway_containers() -> None:
    """
    Builds the Gateway and Link Docker containers.
    """
    client = docker.from_env()
    client.images.build(
        path=get_gateway_resource_path(GATEWAY_DOCKERFILE_PATH), tag=GATEWAY_IMAGE_TAG
    )
    client.images.build(path=get_gateway_resource_path(LINK_DOCKERFILE_PATH), tag=LINK_IMAGE_TAG)


def get_port_from_error(err_msg: str) -> int:
    match = re.search(r"0\.0\.0\.0:(\d+)", err_msg)
    if not match:
        raise ValueError(f"Port number not found in error message: {err_msg}")
    return int(match.group(1))


def launch_gateway(name: str) -> Container:
    build_gateway_containers()

    client = docker.from_env()

    # get or create gateway network
    try:
        network: Network = client.networks.get("fractal-gateway-network")  # type: ignore
    except NotFound:
        network: Network = client.networks.create("fractal-gateway-network", driver="bridge")  # type: ignore

    try:
        gateway = client.containers.run(
            image=GATEWAY_IMAGE_TAG,
            name=name,
            ports={80: 80, 443: 443},
            network=network.name,
            restart_policy={"Name": "always"},
            labels={"f.gateway": "true"},
            detach=True,
            environment={"NGINX_ENVSUBST_OUTPUT_DIR": "/etc/nginx"},
        )
        return gateway  # type: ignore
    except APIError as err:
        container: Container = client.containers.get(name)  # type: ignore
        container.remove()
        port_number = get_port_from_error(err.explanation)  # type: ignore
        if port_number:
            raise PortAlreadyAllocatedError(port_number)
        raise err

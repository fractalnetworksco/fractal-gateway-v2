import os
import socket

import docker
from docker.errors import NotFound
from docker.models.containers import Container
from docker.models.networks import Network

GATEWAY_DOCKERFILE_PATH = "gateway"
GATEWAY_IMAGE_TAG = "fractal-gateway:latest"
LINK_DOCKERFILE_PATH = "gateway-link"
LINK_IMAGE_TAG = "fractal-gateway-link:latest"


def check_port_availability(port: int, host: str = "127.0.0.1"):
    """
    Attempts to connect to a given port on the specified host to infer if the port is in use.

    Parameters:
    - host: String, the hostname or IP address to check the port on. Use 'localhost' or '127.0.0.1' for local checks.
    - port: Integer, the port number to check.

    Returns:
    - True if a connection to the port is successful (indicating something is listening on the port), False otherwise.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)  # Set a timeout to prevent long waits
        try:
            result = sock.connect_ex((host, port))
            if result == 0:
                return False  # Successfully connected, something is listening.
            else:
                return True  # Could not connect, the port might be available.
        except socket.error:
            return True  # Socket error could indicate inability to connect for various reasons.


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


def launch_gateway(name: str) -> Container:
    build_gateway_containers()

    client = docker.from_env()

    # get or create gateway network
    try:
        network: Network = client.networks.get("fractal-gateway-network")  # type: ignore
    except NotFound:
        network: Network = client.networks.create("fractal-gateway-network", driver="bridge")  # type: ignore

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

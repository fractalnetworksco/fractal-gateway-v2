import os
import re
import time
from typing import Any, Optional

import docker
import yaml
from docker import DockerClient
from docker.errors import APIError, NotFound
from docker.models.containers import Container
from docker.models.networks import Network
from fractal.gateway.exceptions import (
    GatewayContainerNotFound,
    GatewayNetworkNotFound,
    PortAlreadyAllocatedError,
)

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


def launch_gateway(container_name: str, labels: Optional[dict[str, Any]] = None) -> Container:
    build_gateway_containers()

    client = docker.from_env()

    if labels is None:
        labels = {"f.gateway": container_name}

    # get or create gateway network
    network_name = "fractal-gateway-network"
    try:
        network: Network = client.networks.get(network_name)  # type: ignore
    except NotFound:
        network: Network = client.networks.create(network_name, driver="bridge")  # type: ignore

    try:
        gateway = client.containers.run(
            image=GATEWAY_IMAGE_TAG,
            name=container_name,
            ports={80: 80, 443: 443},
            network=network.name,
            restart_policy={"Name": "always"},
            labels=labels,
            detach=True,
            environment={"NGINX_ENVSUBST_OUTPUT_DIR": "/etc/nginx"},
        )
        return gateway  # type: ignore
    except APIError as err:
        container: Container = client.containers.get(container_name)  # type: ignore
        container.remove()
        port_number = get_port_from_error(err.explanation)  # type: ignore
        if port_number:
            raise PortAlreadyAllocatedError(port_number)
        raise err


def get_gateway_container(
    name: str = "fractal-gateway", client: Optional[DockerClient] = None
) -> Container:
    """
    Get the container with the specified name from Docker.

    Parameters:
    - name: String, the name of the container to retrieve.
    - client: DockerClient, the Docker client to use for the operation. If not provided, will
        use the default Docker client.

    Returns:
    - Container, the container with the specified name

    Raises:
        GatewayContainerNotFound: If the container with the specified name is not found.
    """
    client = client or docker.from_env()
    try:
        return client.containers.list(filters={"label": "f.gateway"})[0]  # type: ignore
    except NotFound:
        raise GatewayContainerNotFound(name)


def generate_wireguard_keypair(client: Optional[DockerClient] = None) -> tuple[str, str]:
    """
    Generate a WireGuard keypair.

    TODO: Handle generating WireGuard keypairs locally if the environment has WireGuard installed.

    Parameters:
    - client: DockerClient, the Docker client to use for the operation. If not provided, will
        use the default Docker client.

    Returns:
    - tuple[private_key, public_key], a tuple containing the generated private and public keys.
    """
    client = client or docker.from_env()
    command = "bash -c 'wg genkey | tee /dev/stderr | wg pubkey'"

    keypair: bytes = client.containers.run(
        image="fractal-gateway-link:latest",
        entrypoint=command,
        stdout=True,
        stderr=True,
        remove=True,
        detach=False,
    )  # type: ignore

    private_key, public_key = keypair.decode().strip().split("\n")
    return private_key, public_key


def launch_link(
    link_fqdn: str,
    link_pubkey: str,
    client: Optional[DockerClient] = None,
) -> tuple[str, str]:
    """
    Launches a link container with the specified FQDN and public key.

    Returns:
    - tuple[wireguard_pubkey, link_address], a tuple containing the generated WireGuard public key and the link's address.
    """
    client = client or docker.from_env()

    # get or create gateway network
    try:
        network: Network = client.networks.get("fractal-gateway-network")  # type: ignore
    except NotFound:
        raise GatewayNetworkNotFound("fractal-gateway-network")

    link_container_name = "-".join(link_fqdn.split("."[-4:]))

    # FIXME

    try:
        link_container: Container = client.containers.run(
            image=LINK_IMAGE_TAG,
            name=link_fqdn,
            network=network.name,
            restart_policy={"Name": "unless-stopped"},
            cap_add=["NET_ADMIN"],
            labels={"f.gateway.link": "true"},
            tty=True,
            detach=True,
            environment={
                "LINK_CLIENT_WG_PUBKEY": link_pubkey,
            },
            ports={"18521/udp": None},
            remove=False,
        )  # type: ignore
    except APIError as err:
        container: Container = client.containers.get(link_container_name)  # type: ignore
        container.remove()
        port_number = get_port_from_error(err.explanation)  # type: ignore
        if port_number:
            raise PortAlreadyAllocatedError(port_number)
        raise err

    # get port that was assigned by docker
    # FIXME: have to sleep a second to allow the port to be assigned for some reason
    time.sleep(1)
    link_container.reload()
    wireguard_port = link_container.attrs["NetworkSettings"]["Ports"]["18521/udp"][0]["HostPort"]  # type: ignore

    link_container.stop()
    link_container.remove()

    # launch link container but with the port that was assigned by docker
    try:
        link_container: Container = client.containers.run(
            image=LINK_IMAGE_TAG,
            name=link_container_name,
            network=network.name,
            restart_policy={"Name": "unless-stopped"},
            cap_add=["NET_ADMIN"],
            labels={"f.gateway.link": "true"},
            tty=True,
            detach=True,
            environment={
                "LINK_CLIENT_WG_PUBKEY": link_pubkey,
            },
            ports={"18521/udp": int(wireguard_port)},
            remove=False,
        )  # type: ignore
    except APIError as err:
        container: Container = client.containers.get(link_container_name)  # type: ignore
        container.remove()
        port_number = get_port_from_error(err.explanation)  # type: ignore
        if port_number:
            raise PortAlreadyAllocatedError(port_number)
        raise err

    # get generated wireguard pubkey from link container
    command = "bash -c 'cat /etc/wireguard/link0.key | wg pubkey'"
    wireguard_pubkey = link_container.exec_run(command).output.decode().strip()
    return wireguard_pubkey, f"{link_fqdn}:{wireguard_port}"


def generate_link_compose_snippet(
    link_config: dict[str, Any], link_fqdn: str, expose: str
) -> str:
    """
    Generate a docker-compose snippet for a link container using the specified link configuration.

    Parameters:
    - link_config: Dict, the link configuration to use for the snippet. Should contain the following keys:
        - gateway_link_public_key: String, the WireGuard public key for the link.
        - link_address: String, the address for the link (i.e. subdomain.mydomain.com:18521).
        - client_private_key: String, the WireGuard private key for the client.

    Returns:
    - str, the docker-compose YAML snippet for the link container.
    """
    if "localhost" in link_fqdn:
        return f"""
  link:
    image: fractalnetworks/gateway-client:latest
    environment:
      LINK_DOMAIN: {link_fqdn}
      EXPOSE: {expose}
      GATEWAY_CLIENT_WG_PRIVKEY: {link_config['client_private_key']}
      GATEWAY_LINK_WG_PUBKEY: {link_config['gateway_link_public_key']}
      GATEWAY_ENDPOINT: {link_config['link_address']}
      TLS_INTERNAL: true
    cap_add:
      - NET_ADMIN
"""

    return f"""
  link:
    image: fractalnetworks/gateway-client:latest
    environment:
      LINK_DOMAIN: {link_fqdn}
      EXPOSE: {expose}
      GATEWAY_CLIENT_WG_PRIVKEY: {link_config['client_private_key']}
      GATEWAY_LINK_WG_PUBKEY: {link_config['gateway_link_public_key']}
      GATEWAY_ENDPOINT: {link_config['link_address']}
    cap_add:
      - NET_ADMIN
"""

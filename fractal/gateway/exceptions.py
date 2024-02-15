class PortAlreadyAllocatedError(Exception):
    def __init__(self, port: int):
        self.port = port
        super().__init__(f"Port {port} is already allocated")


class GatewayContainerNotFound(Exception):
    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Gateway container with name {name} not found")


class GatewayNetworkNotFound(Exception):
    def __init__(self, network: str):
        self.network = network
        super().__init__(f"Gateway container with name {network} not found")

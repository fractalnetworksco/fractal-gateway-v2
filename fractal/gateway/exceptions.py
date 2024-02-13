class PortAlreadyAllocatedError(Exception):
    def __init__(self, port: int):
        self.port = port
        super().__init__(f"Port {port} is already allocated")

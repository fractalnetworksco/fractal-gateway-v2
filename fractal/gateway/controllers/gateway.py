from fractal.cli import cli_method


class FractalGatewayController:
    PLUGIN_NAME = "gateway"

    @cli_method
    def list(self):
        """
        List Gateways.
        ---
        """
        print("Not implemented")
        exit(0)


Controller = FractalGatewayController

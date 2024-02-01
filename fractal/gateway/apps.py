from django.apps import AppConfig
from django.db.models.signals import post_migrate


class GatewayConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "fractal.gateway"

    # def ready(self):
    #     from fractal.gateway.signals import create_matrix_homeserver_for_default_target

    #     post_migrate.connect(create_matrix_homeserver_for_default_target, sender=self)

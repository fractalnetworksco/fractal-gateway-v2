from django.urls import path
from fractal.gateway.views import WellKnownView

urlpatterns = [
    path(".well-known/matrix/client", WellKnownView.as_view(), name="well-known-matrix-client"),
]

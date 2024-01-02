from django.db import models
from fractal_database.models import ReplicatedModel


class Gateway(ReplicatedModel):
    name = models.CharField(max_length=255)
    primary = models.BooleanField(default=False)


class Link(ReplicatedModel):
    url = models.URLField()
    gateway = models.ForeignKey(Gateway, on_delete=models.CASCADE)

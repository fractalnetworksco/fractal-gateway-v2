# Generated by Django 5.0.3 on 2024-03-18 20:00

import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('fractal_database', '0001_initial'),
        ('fractal_database_matrix', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='GatewayReplicationTarget',
            fields=[
            ],
            options={
                'proxy': True,
                'indexes': [],
                'constraints': [],
            },
            bases=('fractal_database_matrix.matrixreplicationtarget',),
        ),
        migrations.CreateModel(
            name='Gateway',
            fields=[
                ('app_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='fractal_database.app')),
                ('databases', models.ManyToManyField(related_name='gateways', to='fractal_database.database')),
            ],
            options={
                'abstract': False,
            },
            bases=('fractal_database.app',),
        ),
        migrations.CreateModel(
            name='Link',
            fields=[
                ('date_created', models.DateTimeField(auto_now_add=True)),
                ('date_modified', models.DateTimeField(auto_now=True)),
                ('deleted', models.BooleanField(default=False)),
                ('object_version', models.PositiveIntegerField(default=0)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('fqdn', models.CharField(max_length=255)),
                ('gateways', models.ManyToManyField(related_name='links', to='gateway.gateway')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='MatrixHomeserver',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('date_created', models.DateTimeField(auto_now_add=True)),
                ('date_modified', models.DateTimeField(auto_now=True)),
                ('deleted', models.BooleanField(default=False)),
                ('object_version', models.PositiveIntegerField(default=0)),
                ('url', models.URLField()),
                ('name', models.CharField(max_length=255)),
                ('priority', models.PositiveIntegerField(blank=True, default=0, null=True)),
                ('database', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='fractal_database.database')),
                ('gateway', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='homeservers', to='gateway.gateway')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]

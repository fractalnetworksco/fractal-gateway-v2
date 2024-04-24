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
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('date_created', models.DateTimeField(auto_now_add=True)),
                ('date_modified', models.DateTimeField(auto_now=True)),
                ('deleted', models.BooleanField(default=False)),
                ('object_version', models.PositiveIntegerField(default=0)),
                ('name', models.CharField(max_length=255)),
                ('ssh_config', models.JSONField(blank=True, default=dict, null=True)),
                ('databases', models.ManyToManyField(related_name='gateways', to='fractal_database.database')),
                ('devices', models.ManyToManyField(related_name='gateways', to='fractal_database.device')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Link',
            fields=[
                ('date_created', models.DateTimeField(auto_now_add=True)),
                ('date_modified', models.DateTimeField(auto_now=True)),
                ('deleted', models.BooleanField(default=False)),
                ('object_version', models.PositiveIntegerField(default=0)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('fqdn', models.CharField(max_length=255, unique=True)),
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

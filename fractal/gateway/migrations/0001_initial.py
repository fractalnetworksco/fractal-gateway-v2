import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('fractal_database', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Gateway',
            fields=[
                ('service_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='fractal_database.service')),
                ('ssh_config', models.JSONField(default=dict)),
                ('databases', models.ManyToManyField(related_name='gateways', to='fractal_database.database')),
            ],
            options={
                'abstract': False,
            },
            bases=('fractal_database.service',),
        ),
        migrations.CreateModel(
            name='Link',
            fields=[
                ('date_created', models.DateTimeField(auto_now_add=True)),
                ('date_modified', models.DateTimeField(auto_now=True)),
                ('deleted', models.BooleanField(default=False)),
                ('object_version', models.PositiveIntegerField(default=0)),
                ('metadata', models.JSONField(default=dict)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('fqdn', models.CharField(max_length=255, unique=True)),
                ('gateways', models.ManyToManyField(related_name='links', to='gateway.gateway')),
                ('service', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='links', to='fractal_database.serviceinstanceconfig')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]

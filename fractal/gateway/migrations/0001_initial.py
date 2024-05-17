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
                ('database_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='fractal_database.database')),
                ('ssh_config', models.JSONField(blank=True, default=dict, null=True)),
                ('databases', models.ManyToManyField(related_name='gateways', to='fractal_database.database')),
            ],
            options={
                'abstract': False,
            },
            bases=('fractal_database.database',),
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
            ],
            options={
                'abstract': False,
            },
        ),
    ]

from django.db import migrations


def move_m2m_data(apps, schema_editor):
    Gateway = apps.get_model("gateway", "Gateway")
    Database = apps.get_model("fractal_database", "Database")

    for gateway in Gateway.objects.all():
        # Transfer all databases related to this gateway
        for db in gateway.databases.all():
            db.new_gateways.add(gateway)


class Migration(migrations.Migration):

    dependencies = [
        ("fractal_database", "0003_database_new_gateways"),
        ("gateway", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(move_m2m_data),
        migrations.RemoveField(
            model_name="gateway",
            name="databases",
        ),
    ]

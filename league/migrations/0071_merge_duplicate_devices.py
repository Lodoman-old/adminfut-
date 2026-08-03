from django.db import migrations


def merge_duplicate_devices(apps, schema_editor):
    DeviceToken = apps.get_model("league", "DeviceToken")
    device_ids = (
        DeviceToken.objects
        .exclude(device_id="")
        .exclude(device_id=None)
        .values_list("device_id", flat=True)
        .distinct()
    )
    for device_id in device_ids:
        tokens = list(
            DeviceToken.objects
            .filter(device_id=device_id)
            .order_by("-activo", "-actualizado")
        )
        if len(tokens) <= 1:
            continue
        keep = tokens[0]
        for old in tokens[1:]:
            if old.pk == keep.pk:
                continue
            if keep.es_invitado and not old.es_invitado:
                pass
            old.activo = False
            old.save()


class Migration(migrations.Migration):

    dependencies = [
        ("league", "0070_devicetoken_email"),
    ]

    operations = [
        migrations.RunPython(merge_duplicate_devices, migrations.RunPython.noop),
    ]

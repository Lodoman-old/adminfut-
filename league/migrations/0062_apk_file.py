from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('league', '0061_firebase_config'),
    ]

    operations = [
        migrations.AddField(
            model_name='configuracionliga',
            name='apk_file',
            field=models.FileField(blank=True, help_text='APK firmada de la app. Descargable por todos los usuarios desde el menú.', null=True, upload_to='apks/', verbose_name='App Android (APK)'),
        ),
    ]

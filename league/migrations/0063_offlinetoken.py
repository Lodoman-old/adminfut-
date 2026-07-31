import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('league', '0062_apk_file'),
    ]

    operations = [
        migrations.CreateModel(
            name='OfflineToken',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token', models.CharField(max_length=64, unique=True)),
                ('creado', models.DateTimeField(auto_now_add=True)),
                ('expira', models.DateTimeField()),
                ('activo', models.BooleanField(default=True)),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='offline_tokens', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Token Offline',
                'verbose_name_plural': 'Tokens Offline',
            },
        ),
    ]

# Copia este archivo como local_settings.py y ajusta los valores
DATABASES = {
    'default': {
        'ENGINE': 'mssql',
        'NAME': 'AdminFut',
        'USER': 'sa',
        'PASSWORD': 'tu_password',
        'HOST': '.\\SQLEXPRESS',
        'PORT': '',
        'OPTIONS': {
            'driver': 'ODBC Driver 17 for SQL Server',
            'extra_params': 'TrustServerCertificate=yes;',
        },
    }
}

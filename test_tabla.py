import os, sys
os.environ['DJANGO_SETTINGS_MODULE']='league_project.settings'
import django
django.setup()
from django.test import Client
c = Client()
try:
    r = c.get('/tabla-posiciones/')
    print(r.status_code)
    print(r.content[:200])
except Exception as e:
    print('ERR')
    import traceback
    traceback.print_exc()

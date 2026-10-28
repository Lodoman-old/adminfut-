import os
os.environ['DJANGO_SETTINGS_MODULE']='league_project.settings'
import django
django.setup()
from django.test import Client
c = Client()
r = c.get('/accounts/verify/')
print(r.status_code)
if hasattr(r,'url'): print(r.url)
elif hasattr(r,'headers'): print(r.headers.get('Location'))

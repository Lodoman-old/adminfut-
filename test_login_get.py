import os
os.environ['DJANGO_SETTINGS_MODULE']='league_project.settings'
import django
django.setup()
from django.test import Client
c = Client()
r = c.get('/accounts/login/')
print(r.status_code)

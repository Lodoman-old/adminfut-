import os,sys
os.environ['DJANGO_SETTINGS_MODULE']='league_project.settings'
import django
django.setup()
from django.test import Client
c = Client()
try:
    r = c.post('/accounts/login/', {'username':'x','password':'y'})
    print(r.status_code)
    print(r.url)
    print(r.content[:300])
except Exception as e:
    import traceback
    traceback.print_exc()

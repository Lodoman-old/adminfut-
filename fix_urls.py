from pathlib import Path
p = Path(r'C:\Users\lodo1\Desktop\PROYECTOS\PROYECTOS\Personal\AdminFut\league\urls.py')
b = p.read_bytes()
# detect utf-16
if b.startswith(b'\xff\xfe') or b.startswith(b'\xfe\xff'):
    try:
        s = b.decode('utf-16')
    except:
        s = b.decode('utf-8', errors='ignore')
else:
    try:
        s = b.decode('utf-8')
    except:
        s = b.decode('latin-1')
# build correct content
new = '''from django.urls import path
from . import views
from . import api_views

urlpatterns = [
    path("tabla-posiciones/", views.tabla_posiciones, name="tabla_posiciones"),
    path("tabla-goleo/", views.tabla_goleo, name="tabla_goleo"),
    path("tabla-tarjetas/", views.tabla_tarjetas, name="tabla_tarjetas"),
    path("tabla-castigados/", views.tabla_castigados, name="tabla_castigados"),
    path("equipo/<int:pk>/", views.equipo_ficha, name="equipo_ficha"),
]
'''
p.write_text(new, encoding='utf-8')
print('done')

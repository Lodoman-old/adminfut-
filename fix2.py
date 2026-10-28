import subprocess
from pathlib import Path
p = Path(r'C:\Users\lodo1\Desktop\PROYECTOS\PROYECTOS\Personal\AdminFut\league\urls.py')
r = subprocess.run(['git','-C',str(p.parent.parent),'show','3c31dc1:league/urls.py'], stdout=subprocess.PIPE)
s = r.stdout.decode('utf-8', errors='ignore')
# add equipo_ficha
old = '    path("horarios-fijos/", views.horarios_fijos_report, name="horarios_fijos_report"),\n'
new = old + '    path("equipo/<int:pk>/", views.equipo_ficha, name="equipo_ficha"),\n'
if old in s and 'equipo_ficha' not in s:
    s2 = s.replace(old, new)
else:
    # try end
    s2 = s
if 'equipo_ficha' not in s2:
    # append before last ]
    s2 = s2.rstrip()
    if s2.endswith(']'):
        s2 = s2[:-1] + '    path("equipo/<int:pk>/", views.equipo_ficha, name="equipo_ficha"),\n]\n'
p.write_text(s2, encoding='utf-8')
print('done')

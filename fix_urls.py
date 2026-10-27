p = r'C:\Users\lodo1\Desktop\PROYECTOS\PROYECTOS\Personal\AdminFut\league\urls.py'
s = open(p, encoding='utf-8').read()
old = '    path("horarios-fijos/", views.horarios_fijos_report, name="horarios_fijos_report"),\n'
new = '    path("horarios-fijos/", views.horarios_fijos_report, name="horarios_fijos_report"),\n    path("equipo/<int:pk>/", views.equipo_ficha, name="equipo_ficha"),\n'
if old in s and 'equipo_ficha' not in s:
    s = s.replace(old, new)
    open(p, 'w', encoding='utf-8').write(s)
    print('added')
else:
    print('skip')

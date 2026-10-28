import subprocess
r=subprocess.run(['git','-C','C:/Users/lodo1/Desktop/PROYECTOS/PROYECTOS/Personal/AdminFut','show','b52f46a:league/views.py'],stdout=subprocess.PIPE)
data=r.stdout.decode('utf-8',errors='ignore')
idx=data.find('def equipo_ficha')
if idx>=0:
    end=data.find('\n\ndef ',idx+1)
    if end==-1: end=idx+2000
    open('equipo_ficha_b52.py','w',encoding='utf-8').write(data[idx:end])
    print('ok')
else:
    print('no')

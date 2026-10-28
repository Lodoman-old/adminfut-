import subprocess
r=subprocess.run(['git','-C','C:/Users/lodo1/Desktop/PROYECTOS/PROYECTOS/Personal/AdminFut','show','3c31dc1:league/views.py'],stdout=subprocess.PIPE)
data=r.stdout.decode('utf-8',errors='ignore')
with open('league/views.py','w',encoding='utf-8') as f:
    f.write(data)
print('ok')

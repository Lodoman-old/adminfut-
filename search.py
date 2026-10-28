import subprocess
r=subprocess.run(['git','-C','C:/Users/lodo1/Desktop/PROYECTOS/PROYECTOS/Personal/AdminFut','show','3c31dc1:league/views.py'],stdout=subprocess.PIPE)
data=r.stdout.decode('utf-8',errors='ignore')
for i,l in enumerate(data.splitlines()):
    if l.strip().startswith('def tabla'):
        print(i+1,l)
        break
else:
    print('none')

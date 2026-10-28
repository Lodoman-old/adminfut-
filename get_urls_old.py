import subprocess
r=subprocess.run(['git','-C','C:/Users/lodo1/Desktop/PROYECTOS/PROYECTOS/Personal/AdminFut','show','1a9696f:league_project/urls.py'],stdout=subprocess.PIPE)
data=r.stdout.decode('utf-8',errors='ignore')
print(data)

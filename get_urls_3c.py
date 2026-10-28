import subprocess
r=subprocess.run(['git','-C','C:/Users/lodo1/Desktop/PROYECTOS/PROYECTOS/Personal/AdminFut','show','3c31dc1:league_project/urls.py'],stdout=subprocess.PIPE)
print(r.stdout.decode('utf-8',errors='ignore'))

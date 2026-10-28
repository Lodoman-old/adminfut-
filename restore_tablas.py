import subprocess, sys
path = 'C:/Users/lodo1/Desktop/PROYECTOS/PROYECTOS/Personal/AdminFut'
r = subprocess.run(['git','-C',path,'show','3c31dc1:league/views.py'], stdout=subprocess.PIPE)
data = r.stdout.decode('utf-8', errors='ignore')
# extract functions
names = ['tabla_posiciones', 'tabla_goleo', 'tabla_tarjetas', 'tabla_castigados']
out = []
for name in names:
    idx = data.find(f'\ndef {name}(')
    if idx == -1:
        continue
    # find next def at col 0
    # look for \n\ndef 
    end = data.find('\n\ndef ', idx+1)
    if end == -1:
        # try \ndef at start of line
        pass
    if end == -1:
        end = len(data)
    out.append(data[idx:end])
# write to file
with open('league/views.py', 'a', encoding='utf-8') as f:
    f.write('\n\n')
    for o in out:
        f.write(o)
        f.write('\n\n')
print('done')

d=open('league_project/middleware.py',encoding='utf-8').read()
idx=d.find('PREFIJOS_PUBLICOS')
if idx>=0:
    print(d[idx:idx+250])

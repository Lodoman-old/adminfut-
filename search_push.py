import os
for root,dirs,files in os.walk('.'):
    if 'venv' in root or '.git' in root: continue
    for f in files:
        if f.endswith('.py') or f.endswith('.html'):
            p=os.path.join(root,f)
            try:
                with open(p,encoding='utf-8',errors='ignore') as fh:
                    d=fh.read()
                if 'admin_push_logs' in d:
                    print(p)
            except:
                pass

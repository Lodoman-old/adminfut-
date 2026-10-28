import os
for root,dirs,files in os.walk('.'):
    if 'venv' in root or '.git' in root: continue
    for f in files:
        if f.endswith('.html') or f.endswith('.py'):
            p=os.path.join(root,f)
            try:
                with open(p,encoding='utf-8',errors='ignore') as fh:
                    d=fh.read()
                if 'accounts/verify' in d or "biometric_verify" in d:
                    print(p)
            except:
                pass

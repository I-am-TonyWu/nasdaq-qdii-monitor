"""Vendor pinned Fontsource/Radix packages for the existing static frontend."""
import base64
import hashlib
import io
import json
import re
import tarfile
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'web'/'vendor'/'ui'
PACKAGES={'@fontsource-variable/inter':'5.3.0','@radix-ui/colors':'3.0.0'}

def main():
    DEST.mkdir(parents=True,exist_ok=True)
    lock_path=DEST/'asset-manifest.json'
    lock=json.loads(lock_path.read_text('utf-8')) if lock_path.exists() else {}
    for name,version in PACKAGES.items():
        meta=requests.get(f'https://registry.npmjs.org/{name}/{version}',timeout=20)
        meta.raise_for_status();meta=meta.json()
        integrity=meta['dist']['integrity']
        if name in lock and lock[name]['integrity']!=integrity:
            raise ValueError('Pinned package integrity changed')
        download=requests.get(meta['dist']['tarball'],timeout=20);download.raise_for_status()
        algorithm,digest=integrity.split('-',1)
        if algorithm!='sha512' or base64.b64encode(hashlib.sha512(download.content).digest()).decode()!=digest:
            raise ValueError('Package checksum mismatch')
        with tarfile.open(fileobj=io.BytesIO(download.content),mode='r:gz') as archive:
            wanted=['index.css','files/inter-latin-wght-normal.woff2','LICENSE'] if 'fontsource' in name else ['slate.css','teal.css','blue.css','red.css','amber.css','violet.css','LICENSE']
            installed=[]
            for filename in wanted:
                member=archive.getmember('package/'+filename)
                payload=archive.extractfile(member).read()
                if 'fontsource' in name and filename=='index.css':
                    block=re.search(r'/\* inter-latin-wght-normal \*/\s*@font-face\s*\{[^}]+\}',payload.decode())
                    if not block:raise ValueError('Fontsource Latin declaration not found')
                    payload=(block[0]+'\n').encode();filename='latin.css'
                target=DEST/('inter' if 'fontsource' in name else 'radix')/filename
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(payload)
                installed.append({'path':str(target.relative_to(ROOT)).replace('\\','/'),'sha256':hashlib.sha256(payload).hexdigest()})
        lock[name]={'version':version,'integrity':integrity,'license':meta['license'],'url':meta['dist']['tarball'],'files':installed}
    lock_path.write_text(json.dumps(lock,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Vendored Inter 5.3.0 and Radix Colors 3.0.0 with checksums and licenses')

if __name__=='__main__':main()

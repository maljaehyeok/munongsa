"""Render candidate units from private host settings. Never installs or starts them."""
import argparse
import hashlib
import ipaddress
import json
from pathlib import Path, PurePosixPath
import re

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
KEYS={'RELEASE_DIR','VENV_DIR','SERVICE_USER','BRIDGE_GATEWAY','NGINX_PEER','BRIDGE_INTERFACE'}


def render(values):
    if set(values)!=KEYS or not all(isinstance(v,str) and v and not re.search(r'\s',v) for v in values.values()):
        raise ValueError('exact private settings required; no secrets or arbitrary environment entries')
    for key in ('RELEASE_DIR','VENV_DIR'):
        path=PurePosixPath(values[key])
        if not path.is_absolute() or '..' in path.parts or not re.fullmatch(r'/[A-Za-z0-9_./-]+',values[key]):
            raise ValueError('absolute Linux directory required')
    if values['SERVICE_USER'] in ('root','ubuntu') or not re.fullmatch('[a-z_][a-z0-9_-]{0,30}',values['SERVICE_USER']):
        raise ValueError('dedicated non-login account required')
    if not re.fullmatch('[a-zA-Z0-9_.-]{1,15}',values['BRIDGE_INTERFACE']) or values['BRIDGE_INTERFACE']=='lo':
        raise ValueError('Docker bridge interface required')
    networks=[ipaddress.ip_network(v) for v in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')]
    for key in ('BRIDGE_GATEWAY','NGINX_PEER'):
        address=ipaddress.IPv4Address(values[key])
        if not any(address in n for n in networks): raise ValueError('RFC1918 Docker addresses required')
    if values['BRIDGE_GATEWAY']==values['NGINX_PEER']: raise ValueError('host and container addresses must differ')
    manifest=json.loads((HERE/'source-manifest.json').read_text(encoding='utf-8'))
    result={}
    for suffix in ('.service','.socket'):
        text=(HERE/('munongsa-chat-api'+suffix+'.in')).read_text(encoding='utf-8')
        if hashlib.sha256(text.encode()).hexdigest()!=manifest['systemd_templates'][suffix]:
            raise ValueError('template differs from reviewed source')
        for key,value in values.items(): text=text.replace('@'+key+'@',value)
        if re.search(r'@[A-Z_]+@',text) or '\\' in text: raise ValueError('unrendered or non-Linux unit')
        result['munongsa-chat-api'+suffix]=text
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--settings',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve()
    if out.exists() or out.is_relative_to(ROOT): raise ValueError('new private directory outside source checkout required')
    rendered=render(json.loads(a.settings.read_text(encoding='utf-8')))
    out.mkdir(parents=True,mode=0o700)
    for name,text in rendered.items():
        dest=out/name;dest.write_text(text,encoding='utf-8');dest.chmod(0o600)
    print('Candidate units rendered; no installation or service action performed.')

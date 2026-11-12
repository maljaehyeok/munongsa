"""Assemble a private host release from reviewed source and an external corpus.

No network, credentials, service control, DB access or corpus regeneration.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def stage(private_corpus, output):
    corpus, output = Path(private_corpus).resolve(), Path(output).resolve()
    if output.exists() or output.is_relative_to(ROOT):
        raise ValueError('use a new private output directory outside this source checkout')
    if not corpus.is_dir(): raise ValueError('private corpus unavailable')
    manifest = json.loads((HERE/'source-manifest.json').read_text(encoding='utf-8'))
    sources = {}
    for name, expected in manifest['runtime'].items():
        path = ROOT/name if Path(name).name.startswith('rag_') else HERE/Path(name).name
        if path.is_symlink() or digest(path) != expected: raise ValueError('runtime differs from reviewed source: '+name)
        sources[name] = path
    for name, expected in manifest['private_corpus'].items():
        path = corpus/name
        if path.is_symlink() or not path.resolve().is_relative_to(corpus) or digest(path) != expected:
            raise ValueError('private evidence version requires review: '+name)
        sources[name] = path
    # All inputs pass before any output is created. Never copy an entire input tree.
    output.mkdir(parents=True, mode=0o700)
    for name, path in sources.items():
        dest = output/'app'/name; dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,dest); dest.chmod(0o644)
    code = ("import sys,ssl,socket;sys.path.insert(0,sys.argv[1]);"
            "socket.socket=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('network forbidden'));"
            "import rag_api;c=rag_api.load_api_corpus();"
            "assert len(c['documents'])==11 and len(c['chunks'])==70 and not c['excluded'];"
            "old=rag_api.rag_search.load_corpus();assert len(old['documents'])==3 and len(old['chunks'])==23 and not old['excluded'];"
            "print('approved_corpus_verified')")
    subprocess.run([sys.executable,'-I','-B','-c',code,str(output/'app/scripts')],check=True,timeout=30)
    result = {'schema':'munongsa-private-host-release-v1','mode':'local-only',
              'documents':11,'passages':70,'files':{n:digest(output/'app'/n) for n in sources}}
    (output/'manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description='Private evidence required; no installation or service changes')
    p.add_argument('--private-corpus',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=stage(a.private_corpus,a.output)
    print(json.dumps({'documents':r['documents'],'passages':r['passages'],'files':len(r['files'])}))

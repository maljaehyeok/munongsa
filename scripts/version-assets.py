"""Deterministic asset identifiers. Run after editing web sources, before release."""
import hashlib,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'index.html';raw=p.read_bytes();text=raw.decode('utf8')
def replace(m):
 file=ROOT/m[2];assert file.is_file(),file
 return m[1]+m[2]+'?v='+hashlib.sha256(file.read_bytes()).hexdigest()[:12]+m[3]
text=re.sub(r'((?:src|href)=["\']\./)(assets/[A-Za-z0-9_.-]+\.(?:js|css))(?:\?[^"\']*)?(["\'])',replace,text)
p.write_bytes(text.encode('utf8'))
print('versioned CSS/JS references by content SHA-256')

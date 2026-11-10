"""Start the existing WSGI adapter using only a systemd-provided loopback socket.

Must run inside PrivateNetwork=yes. No new TCP listener is created here.
"""
import errno
from pathlib import Path
import socket
import sys


def verify_private_network():
    interfaces={line.split(':',1)[0].strip() for line in Path('/proc/net/dev').read_text().splitlines() if ':' in line}
    if interfaces!={'lo'}:
        raise RuntimeError('private_network_interfaces_invalid')
    for line in Path('/proc/net/route').read_text().splitlines()[1:]:
        if line.split() and line.split()[0]!='lo':
            raise RuntimeError('non_loopback_route_present')
    test=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    try:
        test.settimeout(1)
        # RFC 5737 documentation address; syscall/route denial must happen locally.
        code=test.connect_ex(('192.0.2.1',9))
        if code not in (errno.EPERM,errno.EACCES,errno.ENETUNREACH,errno.EHOSTUNREACH):
            raise RuntimeError('outbound_denial_not_proven')
    finally:test.close()
    return True


def main():
    try:
        verify_private_network()
        # env -i deliberately removes LISTEN_*; the single socket is always FD 3.
        listener=socket.socket(fileno=3)
        if listener.family!=socket.AF_INET or listener.getsockname()!=('127.0.0.1',8765):
            raise RuntimeError('activated_socket_not_loopback')
        if listener.getsockopt(socket.SOL_SOCKET,socket.SO_TYPE)!=socket.SOCK_STREAM:
            raise RuntimeError('activated_socket_not_tcp')
        import chat_wsgi
        return chat_wsgi.main(inherited_socket=listener)
    except Exception as exc:
        reason=str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__
        print('Isolated API startup stopped: '+reason,file=sys.stderr)
        return 2


if __name__=='__main__':raise SystemExit(main())

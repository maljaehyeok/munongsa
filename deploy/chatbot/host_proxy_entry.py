"""Persistent isolated API entrypoint; uses an inherited bridge-only TCP socket."""
import argparse
import ipaddress
import json
import socket
import sys


class PeerOnly:
    def __init__(self, app, peer):
        self.app,self.peer=app,peer

    def __call__(self, env, start_response):
        # Actual socket peer; forwarded headers cannot grant access.
        if env.get('REMOTE_ADDR')!=self.peer:
            body=json.dumps({'mode':'local','status':'error','answer':'허용된 웹서버 경로로 이용해 주세요.',
                             'programs':[],'sources':[]},ensure_ascii=False).encode('utf-8')
            start_response('403 Forbidden',[('Content-Type','application/json; charset=utf-8'),
                ('Content-Length',str(len(body))),('Cache-Control','no-store')])
            return [body]
        return self.app(env,start_response)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--bind-address',required=True)
    parser.add_argument('--nginx-peer',required=True)
    args=parser.parse_args()
    try:
        address=ipaddress.IPv4Address(args.bind_address)
        peer=ipaddress.IPv4Address(args.nginx_peer)
        if not address.is_private or address.is_loopback or not peer.is_private or address==peer:
            raise RuntimeError('invalid_private_bridge_addresses')
        from host_socket_entry import verify_private_network
        verify_private_network()
        listener=socket.socket(fileno=3)
        if listener.family!=socket.AF_INET or listener.getsockname()!=(str(address),8765):
            raise RuntimeError('activated_socket_address_mismatch')
        if listener.getsockopt(socket.SOL_SOCKET,socket.SO_TYPE)!=socket.SOCK_STREAM:
            raise RuntimeError('activated_socket_not_tcp')
        import chat_wsgi
        return chat_wsgi.main(inherited_socket=listener,
                              application_wrapper=lambda app:PeerOnly(app,str(peer)))
    except Exception as exc:
        reason=str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__
        print('Isolated proxy API startup stopped: '+reason,file=sys.stderr)
        return 2


if __name__=='__main__':raise SystemExit(main())

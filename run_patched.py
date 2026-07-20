import socket
import sys

original_getaddrinfo = socket.getaddrinfo

def patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if host == 'aws-0-us-west-2.pooler.supabase.com':
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('54.70.143.232', port))]
    return original_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = patched_getaddrinfo

if __name__ == "__main__":
    sys.argv = ['manage.py'] + sys.argv[1:]
    with open('manage.py') as f:
        code = compile(f.read(), 'manage.py', 'exec')
        exec(code)

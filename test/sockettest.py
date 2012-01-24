import logging
import kaa
from kaa.net.tls import TLSSocket

log = logging.getLogger('tls').ensureRootHandler()

@kaa.coroutine()
def new_client(client):
    ip, port = client.peer[:2]
    print 'New connection from %s:%s' % (ip, port)
    #yield client.starttls_server()
    client.write('Hello %s, connecting from port %d\n' % (ip, port))

    remote = TLSSocket()
    yield remote.connect('www.google.com:443')
    yield remote.starttls_client()
    yield remote.write('GET / HTTP/1.0\n\n')
    while remote.readable:
        data = yield remote.read()
        yield client.write(data)
    client.write('\n\nBye!\n')
    client.close()

server = kaa.Socket()
server.signals['new-client'].connect(new_client)
server.listen(8080)
print "Connect to localhost:8080"
kaa.main.run()

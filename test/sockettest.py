import kaa

@kaa.coroutine()
def new_client(client):
    ip, port = client.address
    print 'New connection from %s:%s' % (ip, port)
    client.write('Hello %s, connecting from port %d\n' % (ip, port))

    remote = kaa.Socket()
    yield remote.connect('www.freevo.org:80')
    remote.write('GET / HTTP/1.0\n\n')
    while remote.connected:
        data = yield remote.read()
        client.write(data)
    client.write('\n\nBye!\n')
    client.close()

server = kaa.Socket()
server.signals['new-client'].connect(new_client)
server.listen(8080)
print "Connect to localhost:8080"
kaa.main.run()

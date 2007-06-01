import kaa.notifier
import kaa.xmlrpc
import sys

# server ##########################

class MyClass(object):

    @kaa.xmlrpc.expose('a.my-foo')
    def foo(self, x, y):
        return x + y
    
    @kaa.xmlrpc.expose('b.my-foo')
    def foo2(self, x, y):
        return x * y
    
# create server
server = kaa.xmlrpc.Server(("localhost", 8000), auth_secret='foo')
# connect MyClass
server.connect(MyClass())

# client ##########################

def test1(r):
    print r
    c.rpc('b.my-foo', 2, 3).connect(test2)

def test2(r):
    print r
    sys.exit(0)


c = kaa.xmlrpc.Client(("localhost", 8000), auth_secret='foo')
c.rpc('a.my-foo', 2, 3).connect(test1)

kaa.notifier.loop()

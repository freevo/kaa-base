import sys
from kaa import xml

x = xml.Document(sys.argv[1], 'freevo')

for c in x.children:
    print c.name, c.type, c.parent.name
print

for c in x:
    print c.name, c.type
print

for c in x.children:
    if c.name == 'movie':
        print 'title is', c.getattr('title')
        for y in c.get_child('info').children:
            print y.name, y.content, type(y.content)
print
        


x = xml.Document(root='freevo')

c = xml.Node('foo')
c.content = "hallo"

x.add_child(c)
x.add_child('foo').add_child('x')
x.add_child('bar', 'text')
x.add_child('hi', x='y').setattr('7', 7)
x.add_child('last', 'text', x='y')

print x

x.save('foo')

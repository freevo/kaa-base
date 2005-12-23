VALUE       = 0
TYPE        = 1
DESCRIPTION = 2
DEFAULT     = 3

class Group(object):
    def __init__(self, schema):
        self.__dict = {}
        self.__vars = []
        for data in schema:
            # add special unicode/string conversion
            self.__dict[data[0]] = [ data[TYPE](data[DEFAULT]) ] + list(data[1:])
            self.__vars.append(data[0])
            

    def add_group(self, name, group, description):
        self.__dict[name] = [ group, Group, description, group ]
        self.__vars.append(name)


    def extract(self, prefix=''):
        ret = []
        for var in self.__vars:
            info = self.__dict[var]
            if info[TYPE] == Group:
                ret += info[VALUE].extract(var.upper() + '_')
            else:
                ret.append((prefix + var.upper(), info[VALUE]))
        return ret
    

    def save(self, filename='', prefix=''):
        """
        Save file. If filename is not given, return the config as string.
        """
        ret = []
        for var in self.__vars:
            info = self.__dict[var]
            name = prefix + var
            desc = info[DESCRIPTION].replace('\n', '\n# ')
            if info[TYPE] == Group:
                ret.append('#\n# SECTION %s\n# %s\n#\n' % (name, desc))
                ret.append(info[VALUE].save(prefix=name + '.'))
            elif info[VALUE] == info[DEFAULT]:
                # add special unicode/string conversion
                ret.append('# %s\n# %s = %s\n' % (desc, name, info[VALUE]))
            else:
                # add special unicode/string conversion
                ret.append('# %s\n%s = %s\n' % (desc, name, info[VALUE]))
        if not filename:
            return '\n'.join(ret)
        f = open(filename, 'w')
        f.write('\n'.join(ret))
        f.close()


    def load(self, filename):
        f = open(filename)
        for line in f.readlines():
            if line.find('#') >= 0:
                line = line[:line.find('#')]
            line = line.strip()
            if not line:
                continue
            if line.count('=') != 1:
                print 'skip line %s' % line
                continue
            key, value = line.split('=')
            key = key.strip()
            value = value.strip()
            object = self
            while key.find('.') != -1:
                object = getattr(object, key[:key.find('.')])
                key = key[key.find('.')+1:]
            setattr(object, key, value)
        f.close()
        
    def __setattr__(self, key, value):
        if key.startswith('_'):
            return object.__setattr__(self, key, value)
        var = self.__dict[key]
        if not isinstance(value, var[TYPE]):
            # This could crash, but that is ok
            value = var[TYPE](value)
        var[VALUE] = value


    def __getattr__(self, key):
        return self.__dict[key][VALUE]


    def getattr(self, key):
        return self.__dict[key]


# TEST CODE

schema = [
    ('foo', int, 'some text', 5),
    ('bar', unicode, 'more text\ndescription has two lines', 'bar' ),
    ('subgroup', Group, 'this is a subgroup',
     [ ( 'x', int, 'descr_x', 7),
       ( 'y', int, 'descr_y', 8),
       ( 'z', Group, 'subsubgroup',
         [ ( 'a', int, 'descr a', 3 ) ] ) ] ) ]

config = Group(schema)
print config.foo
print config.getattr('foo')

config.foo = 10
print config.foo
# This crahes because hello is no int
try:
    config.foo = 'hello'
except Exception, e:
    print e
print config.subgroup.x
config.subgroup.x = 10
print config.subgroup.x

# create new group on the fly
dvb_schema = [
    ('card', int, 'card number', 0),
    ('priority', int, 'card priority', 6) ]
    
dvb0 = Group(dvb_schema)
dvb1 = Group(dvb_schema)
dvb1.card = 1

config.add_group('dvb0', dvb0, 'dvb card 0')
config.add_group('dvb1', dvb1, 'dvb card 1')

print config.dvb0.priority
print config.dvb1.card
dvb0.priority = 10
print config.dvb0.priority
print
print 'Variables:'
for v in config.extract():
    print v
print

print 'config.subgroup.z.a is', config.subgroup.z.a
print 'set to 5'
config.subgroup.z.a = 5
print 'config.subgroup.z.a is', config.subgroup.z.a

print 'save config to filename config.test'
config.save('config.test')
print 'create new config object'
config = Group(schema)
config.add_group('dvb0', dvb0, 'dvb card 0')
config.add_group('dvb1', dvb1, 'dvb card 1')
print 'config.subgroup.z.a is', config.subgroup.z.a
print 'read config file into new object'
config.load('config.test')
print 'config.subgroup.z.a is', config.subgroup.z.a

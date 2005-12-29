import copy

class Var(object):
    def __init__(self, name, type, descr='', default=None):
        self.name  = name
        self.type  = type
        self.descr = descr
        self.default = default
        self.value = default
        
class Group(object):
    def __init__(self, schema):
        self.__dict = {}
        self.__vars = []
        for data in schema:
            # add special unicode/string conversion
            self.__dict[data.name] = data
            self.__vars.append(data.name)
            

    def add_group(self, name, group, description):
        self.__dict[name] = Var(name, Group, description, group)
        self.__vars.append(name)


    def extract(self, prefix=''):
        ret = []
        for var in self.__vars:
            info = self.__dict[var]
            if info.type == Group:
                ret += info.value.extract(prefix + var.upper() + '_')
            else:
                ret.append((prefix + var.upper(), info.value))
        return ret
    

    def save(self, filename='', prefix=''):
        """
        Save file. If filename is not given, return the config as string.
        """
        ret = []
        for var in self.__vars:
            info = self.__dict[var]
            name = prefix + var
            desc = info.descr.replace('\n', '\n# ')
            if info.type == Group:
                ret.append('#\n# SECTION %s\n# %s\n#\n' % (name, desc))
                ret.append(info.value.save(prefix=name + '.'))
            elif info.value == info.default:
                # add special unicode/string conversion
                ret.append('# %s\n# %s = %s\n' % (desc, name, info.value))
            else:
                # add special unicode/string conversion
                ret.append('# %s\n%s = %s\n' % (desc, name, info.value))
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
        if not isinstance(value, var.type):
            # This could crash, but that is ok
            value = var.type(value)
        var.value = value


    def __getattr__(self, key):
        return self.__dict[key].value


    def getattr(self, key):
        return self.__dict[key]


# TEST CODE

config = Group([
    Var(name='foo', type=int, descr='some text', default=5),
    Var(name='bar', type=unicode, default='bar',
        descr='more text\ndescription has two lines')])

subgroup = Group( [
    Var(name='x', type=int, descr='descr_x', default=7 ),
    Var(name='y', type=int, descr='descr_y', default=8 ) ])
config.add_group('subgroup', subgroup, 'this is a subgroup')

subsubgroup = Group( [
    Var(name='a', type=int, descr='descr a', default=3 ) ])
subgroup.add_group('z', subsubgroup, 'desrc of subsubgroup')

print config.foo
print config.getattr('foo')

config.foo = 10
print config.foo
# This crashes because hello is no int
try:
    config.foo = 'hello'
except Exception, e:
    print e
print config.subgroup.x
config.subgroup.x = 10
print config.subgroup.x

# create new group on the fly
dvb_schema = [
    Var(name='card', type=int, descr='card number', default=0 ),
    Var(name='priority', type=int, descr='card priority', default=6) ]
    
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
print 'change config object'
config.subgroup.z.a = 6
print 'config.subgroup.z.a is', config.subgroup.z.a
print 'read config file into new object'
config.load('config.test')
print 'config.subgroup.z.a is', config.subgroup.z.a

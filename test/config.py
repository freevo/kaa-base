# -*- coding: iso-8859-1 -*-

from kaa.config import Var, Group, Dict, List, Config


def config_change_cb(name, oldval, newval):
    print "******* CFG ITEM CHANGE", name, oldval, newval

config = Config(desc='basic config group', schema=[
    Var(name='foo', desc='some text', default=5),
    Var(name='bar', default=u'bar',
        desc='more text\ndescription has two lines'),

    # group defined inside the basic schema
    Group(name='inline', desc='this is a subgroup', schema=[
    Var(name='x', desc='desc_x', default=7 ),
    Var(name='y', type=range(0,5), desc='desc_y', default=3 ) ])
    ])


# create extra group and add it to the schema
subgroup = Group(desc='this is a subgroup', schema=[
    Var(name='x', desc=u'desc_x with non ascii ü', default=7 ),
    # the next variable allows numbers from 0-4
    Var(name='y', type=range(0,5), desc='desc_y', default=3 ) ])
config.add_variable('subgroup', subgroup)

# create a group again deeper in the tree
subsubgroup = Group(desc='desrc of subsubgroup', schema=[
    Var(name='a', desc='desc a', default=3 ) ])
subgroup.add_variable('z', subsubgroup)

# create a list of a group
l = List(desc='desrc of list subsubgroup', schema=Group([
    Var(name='a', type=int, desc='desc a', default=3 ),
    # z is again a group
    Group(name='z', desc='this is a subgroup', schema=[
    Var(name='x', desc='desc_x', default=7 ),
    Var(name='y', type=range(0,5), desc='desc_y', default=3 ) ]) ]))
subgroup.add_variable('list', l)

# create a dict of strings
epg = Dict(desc='desrc of dict epg', schema=Var(default=''))
subgroup.add_variable('epg', epg)

# store the schema up to this point, we will need it later
part_config = config.copy()

# create extra group and add it to the schema
subgroup = Group(desc='this is a subgroup', schema=[
    Var(name='x', desc='desc_x', default=7 ) ])
config.add_variable('some_group', subgroup)

# OK, let's play with the config

config.subgroup.list.add_monitor(config_change_cb)
config.add_monitor(config_change_cb)
print '** Test 1: change config.subgroup.list and create some errors **'
print config.subgroup
print config.subgroup.list
print config.subgroup.list[0]
print config.subgroup.list[0].a
config.subgroup.list[0].a = 6
print config.subgroup.list[0].a

# This crashes because there is no .a
try:
    config.subgroup.list[1].z.a = 7
except Exception, e:
    print e

# This crashes because the index is no int
try:
    config.subgroup.list['foo'].z.x = 7
except Exception, e:
    print e

print config.subgroup.list[1].z.x
config.subgroup.list[1].z.x = 8
print config.subgroup.list[1].z.x

print
print '** Test 2: play with the dict **'

epg['foo'] = 'bar'
epg['x']   = u'non-ascii: ö'
epg[u'also-non-ascii ä'] = u'non-ascii: ö'
epg['this.has.a.dot'] = 'something'
epg['this.has.a.='] = 'something'
epg['the other way around'] = 'something=bar'

print epg['foo']
print
for key, value in epg.items():
    print key, value
print
for key in epg:
    print key
for var in epg.values():
    print var
print
print '** Test 3: play some other variables **'

print config.foo

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

print 'y', config.subgroup.y
# This crashes because 8 is not in range
try:
    config.subgroup.y = 8
except TypeError, e:
    print e
print 'y', config.subgroup.y
config.subgroup.y = 2
print 'y', config.subgroup.y

try:
    config.not_there
except Exception, e:
    print e

config.some_group.x = 1

print
print '** Test 4: save and reload **'

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
if not config.load('config.test'):
    print 'load error, bad lines saved, not expected'
print 'config.subgroup.z.a is', config.subgroup.z.a
print 'load again in incomplete schema'
if not part_config.load('config.test'):
    print 'load error, bad lines saved as expected'
print isinstance(config.subgroup.z.a, str)
part_config.save('config.test2')

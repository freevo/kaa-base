# -*- coding: iso-8859-1 -*-

from kaa.config import Var, Group, Dict, Config

config = Config(desc='mplayer configuration', schema=[

  Var(name='activate', desc='activate backend', default=True),

  Dict(name='dict', schema=Var(default=''), defaults = {'x': 'foo', 'y': 'yyy'}),

  Dict(name='dictgroup', schema=Group(schema = [
    Var(name='x', default=True),
    Var(name='y', default=True)])),

  Dict(name='dictdict', schema=Dict(name='foo', schema=Var(default='')))

])

config.dict['f'] = 'd'
config.dict['z'] = 'j'

config.dictdict['a']['f'] = 'd'
config.dictdict['b']['z'] = 'j'

config.dictgroup['c'].x = False
config.dictgroup['d'].y = 'j'

print config.dictdict['a']['f']
print 'save'
config.save('x.cfg')

print 'load'
config.load('x.cfg')

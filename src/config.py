# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# config.py - config file reader
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# Copyright 2006-2009 Dirk Meyer, Jason Tackaberry
#
# Please see the file AUTHORS for a complete list of authors.
#
# This library is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version
# 2.1 as published by the Free Software Foundation.
#
# This library is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301 USA
#
# -----------------------------------------------------------------------------

__all__ = [ 'Var', 'Group', 'Dict', 'List', 'Config', 'set_default',
            'get_description', 'get_config', 'get_schema',  'get_type',
            'DELETED', 'DEFAULT' ]

# Python imports
import os
import re
import copy
import logging
import stat
import hashlib
import textwrap
from new import classobj

# kaa.base modules
from strutils import str_to_unicode, unicode_to_str, get_encoding
from callable import Callable, WeakCallable
from timer import WeakTimer, WeakOneShotTimer
from kaa.base.inotify import INotify
from utils import property
import main

# get logging object
log = logging.getLogger('config')

# align regexp
align = re.compile(u'\n( *)[^\n]', re.MULTILINE)

# Monitors will be notified a Var is set to DELETED just before it is deleted
# from either a list or dictionary.
DELETED = object()
# Special value to revert a Var to its default value.
DEFAULT = object()


def _format(text):
    """
    Format a description with multiple lines.
    """
    if text.find('\n') == -1:
        return text.strip()

    # This can happen if you use multiple lines and use the python
    # code formating. So there are spaces at each line. Find the maximum
    # number of spaces to delete.

    # description with more than one line, format the text
    if not text.startswith(u'\n'):
        # add newline at the beginning for regexp
        text = u'\n' + text
    # align desc
    strip = 100
    for m in align.findall(text, re.MULTILINE):
        strip = min(len(m), strip)
    if strip == 100 or strip < 1:
        # nothing found
        return text.strip()

    newtext = []
    for line in text.split(u'\n'):
        newtext.append(line[strip+1:])
    return u'\n'.join(newtext)[1:].strip()


class Base(object):
    """
    Base class for all config objects.
    """

    def __init__(self, name='', desc=u'', default=None):
        super(Base, self).__init__()
        self._parent = None
        # This name is not authoritative, but rather is the name we should have
        # in our parent's namespace once added.  For variables under a
        # Container, _name is None.
        self._name = name
        self._desc = _format(str_to_unicode(desc))
        self._default = default
        self._value = default
        self._monitors = []


    def _hash(self, values=True):
        """
        Returns a hash of the config item.

        If values is False, don't include the value in the hash, effectively taking
        a hash of the schema only.
        """
        value = repr(self._value) if values else ''
        return hashlib.md5(repr(self._desc) + repr(self._default) + value).hexdigest()


    def __getstate__(self):
        """
        Called during deepcopy.  Ensure we don't copy monitors.
        """
        state = self.__dict__.copy()
        state['_monitors'] = []
        return state


    def copy(self):
        """
        Return a deep copy of the object.  Monitor callbacks are not copied.
        """
        return copy.deepcopy(self)

    def add_monitor(self, callback):
        # Wrap the function or method in a class that will ignore deep copies
        # because deepcopy() is unable to copy callables.
        self._monitors.append(Callable(callback))

    def remove_monitor(self, callback):
        for monitor in self._monitors:
            if callback == monitor:
                self._monitors.remove(monitor)

    def _notify_monitors(self, oldval, newval):
        o = self
        name = self._get_fqname() or None
        while o:
            for monitor in o._monitors:
                monitor(name, oldval, newval)
            o = o._parent


    @property
    def parent(self):
        return self._parent


    def __repr__(self):
        return repr(self._value)


    def _get_fqname(self, child=None):
        """
        Returns a fully qualified name for the variable.
        """
        if not self._parent:
            return
        return self._parent._get_fqname(self)
        

class VarProxy(Base):
    """
    Wraps a config variable value, inheriting the actual type of that
    value (int, str, unicode, etc.) and offers add_monitor and remove_monitor
    methods to manage the monitor list of the original Var object.
    """
    def __new__(cls, item):
        clstype = realclass = type(item._value)
        if clstype == bool:
            # You can't subclass a boolean, so use int instead.  In practice,
            # this isn't a problem, since __class__ will end up being bool,
            # thanks to __getattribute__, so isinstance(o, bool) will be True.
            clstype = int

        newclass = classobj("VarProxy", (clstype, cls), {
            "__getattribute__": cls.__getattribute__,
            "__str__": cls.__str__,
        })

        if item._value:
            self = newclass(item._value)
        else:
            self = newclass()

        # Merge Base dictionary (for better introspection)
        self.__dict__.update(Base.__dict__)
        self._class = realclass
        return self


    def __init__(self, value = None):
        if not isinstance(value, Var):
            # Called inside __new__ when we pass the intrinsic value for this
            # config variable
            super(VarProxy, self).__init__(default = value)
        else:
            # Called implicitly after returning from __new__, here value will
            # be a kaa.config.Var
            self._monitors = value._monitors
            self._parent = value._parent
            self._item = value


    def __getattribute__(self, attr):
        if attr == "__class__":
            return super(VarProxy, self).__getattribute__("_class")
        return super(VarProxy, self).__getattribute__(attr)

    def __str__(self):
        return self._class.__str__(self)

    def __repr__(self):
        return self._class.__repr__(self)


class Var(Base):
    """
    A config variable.
    """
    def __init__(self, name='', type='', desc=u'', default=None):
        super(Var, self).__init__(name, desc, default)
        if type == '':
            # create type based on default
            if default == None:
                raise AttributeError('define type or default')
            type = default.__class__

        self._type = type


    def _hash(self, values=True):
        """
        Returns a hash of the config item.
        """
        return hashlib.md5(super(Var, self)._hash(values) + repr(self._type)).hexdigest()

    def __eq__(self, value):
        return self._value == value

    def _stringify(self, print_desc=True):
        """
        Convert object into a string to write into a config file.
        """
        # create description
        desc = ''
        if print_desc:
            if self._desc:
                desc = '# | %s\n' % unicode_to_str(self._desc).replace('\n', '\n# | ')
                if isinstance(self._type, (tuple, list)):
                    # Show list of allowed values for this tuple variable.
                    if type(self._type[0]) == type(self._type[-1]) == int and \
                       self._type == range(self._type[0], self._type[-1]):
                        # Type is a range
                        allowed = '%d-%d' % (self._type[0], self._type[-1])
                    else:
                        allowed = ', '.join([ str(x) for x in self._type ])
                    allowed = textwrap.wrap(allowed, 78,
                                          initial_indent = '# | Allowed values: ',
                                          subsequent_indent = '# |' + 17 * ' ')
                    desc += '\n'.join(allowed) + '\n'

                if self._value != self._default:
                    # User value is different than default, so include default
                    # in comments for reference.
                    desc += '# | Default: ' + str(self._default) + '\n'

        value = unicode_to_str(self._value)
        if self._value == self._default:
            value = '<default: %s>' % (value if value != '' else '(empty string)')
        return '%s%s = %s' % (desc, unicode_to_str(self._get_fqname()), value)


    def _cfg_set(self, value, default=False):
        """
        Set variable to value. If the value's type is not right, TypeError will
        be raised (however string and unicode will be coerced into each other
        if necessary).  If default is set to True, the default value will also
        be changed.
        """
        if value is DEFAULT:
            value = self._default
        elif value is DELETED:
            self._notify_monitors(self._value, DELETED)
            return

        if isinstance(self._type, (list, tuple)):
            if not value in self._type:
                # This could crash, but that is ok
                value = self._type[0].__class__(value)
            if not value in self._type:
                allowed = [ str(x) for x in self._type ]
                raise TypeError('Variable must be one of %s' % ', '.join(allowed))
        elif not isinstance(value, self._type):
            if self._type == str:
                value = unicode_to_str(value)
            elif self._type == unicode:
                value = str_to_unicode(value)
            elif self._type == bool:
                if not value or value.lower() in ('0', 'false', 'no'):
                    value = False
                else:
                    value = True
            else:
                # This could crash, but that is ok
                value = self._type(value)
        if default:
            self._default = value
        if self._value != value:
            oldval, self._value = self._value, value
            self._notify_monitors(oldval, value)
        return value


class Group(Base):
    """
    A config group.
    """
    def __init__(self, schema, desc=u'', name='', desc_type='default'):
        super(Group, self).__init__(name, desc)
        self._dict = {}
        self._vars = []
        self._schema = schema
        # 'default' will print all data
        # 'group' will only print the group description
        self._desc_type = desc_type

        for data in schema:
            if not data._name:
                raise AttributeError('Variable within group "%s" is missing name.' % name)
            if data._name in self.__class__.__dict__:
                raise ValueError('Config name "%s" conflicts with internal method or property' % data._name)
            self._dict[data._name] = data
            self._vars.append(data._name)

        # the value of a group is the group itself
        # FIXME: cycle.
        self._value = self

        # Parent all the items in the schema
        # FIXME: cycle.
        for item in schema:
            item._parent = self


    def _get_fqname(self, child=None):
        childname = [k for k,v in self._dict.items() if v is child][0] if child else ''
        if not self._parent:
            return childname
        return (self._parent._get_fqname(self) + '.' + childname).strip('.')


    def add_variable(self, name, value):
        """
        Add a variable to the group. The name will be set into the
        given value. The object will _not_ be copied.
        """
        if name in self.__class__.__dict__:
            raise ValueError('Config name "%s" conflicts with internal method or property' % name)
        value._parent = self
        self._dict[name] = value
        self._vars.append(name)


    @property
    def variables(self):
        """
        List of variables for this group.
        """
        return self._vars


    def _hash(self, values=True):
        """
        Returns a hash of the config item.
        """
        hash = hashlib.md5(super(Group, self)._hash(values))
        for name in self._vars:
            hash.update(name + self._dict[name]._hash(values))
        return hash.hexdigest()


    def _stringify(self, print_desc=True):
        """
        Convert object into a string to write into a config file.
        """
        ret  = []
        desc = unicode_to_str(self._desc.strip('\n')).replace('\n', '\n# | ')
        fqn = self._get_fqname()
        is_anonymous = fqn.endswith(']')

        if print_desc and fqn and not is_anonymous:
            sections = [x.capitalize() for x in fqn.split('.')]
            breadcrumb = ' > '.join(sections)
            ret.append('#\n# Begin Group: %s' % breadcrumb)

        print_var_desc = print_desc

        if fqn and desc and not is_anonymous and print_desc:
            ret.append('# | %s\n#' % desc)
            if self._desc_type != 'default':
                print_var_desc = False

        # Iterate over group vars and fetch their cfg strings, also
        # deterining if we need to space them (by separating with a
        # blank commented line), which we do if
        var_strings = []
        space_vars = False
        n_nongroup = 0
        for name in self._vars:
            var = self._dict[name]
            var_is_group = isinstance(var, (Group, Container))
            cfgstr = var._stringify(print_var_desc)
            if not var_is_group:
                n_nongroup += 1
                space_vars = space_vars or '\n' in cfgstr
            var_strings.append((cfgstr, var_is_group))

        for (cfgstr, var_is_group) in var_strings:
            if var_is_group and (not ret or not ret[-1].endswith('\n')):
                # Config item is a group or list, space it down with a blank
                # line for readability.
                ret.append('')
            elif '\n' in cfgstr:
                ret.append('')
            ret.append(cfgstr)

        if print_desc and fqn and not is_anonymous:
            if n_nongroup != len(self._vars) and (not ret or not ret[-1].endswith('\n')):
                # One of our variables is a group/dict, so add another
                # empty line to separate the stanza.
                ret.append('')
            elif not space_vars or n_nongroup <= 1:
                ret.append('#')
            ret.append('#\n# End Group: %s\n#' % breadcrumb)
        return '\n'.join(ret)


    def _cfg_get(self, key):
        """
        Get variable, subgroup, dict or list object (as object not value).
        """
        if key not in self._dict:
            if key.replace('_', '-') in self._dict:
                return self._dict[key.replace('_', '-')]
            return object.__getattribute__(self, key)
        return self._dict[key]


    def __setattr__(self, key, value):
        """
        Set a variable in the group.
        """
        if key.startswith('_') or key not in self._dict:
            return object.__setattr__(self, key, value)
        self._cfg_get(key)._cfg_set(value)


    def __getattr__(self, key):
        """
        Get variable, subgroup, dict or list.
        """
        if key.startswith('_'):
            return object.__getattribute__(self, key)
        item = self._cfg_get(key)
        if isinstance(item, Var):
            return VarProxy(item)
        return item

    def __repr__(self):
        return repr(self._dict)


    def __iter__(self):
        return self._vars.__iter__()


class Container(Base):
    """
    "Abstract" base class for containers like dict and list.

    Subclasses must implement:
        _real_cfg_get(key):
            returns the cfg Var for the given key (or index)

        _cfg_set_item(key, var):
            sets the cfg Var for the given key (or index)

        _vars():
            iterator producing all Vars in container as (key/index, var)
    """
    def __init__(self, name, desc, schema, type, defaults):
        super(Container, self).__init__(name, desc)
        if isinstance(schema, (list, tuple)):
            # Wrap all the given config objects into a group.
            schema = Group(schema=schema, desc=desc, name=name)
        self._schema = schema
        self._type = type
        self._value = self
        schema._parent = self

        for key, value in defaults:
            # FIXME: how to handle complex dict defaults with a dict in
            # dict or group in dict?
            var = self._cfg_get(key)
            var._default = var._value = value


    def _get_fqname(self, child=None):
        childname = '[%s]' % [k for k,v in self._vars() if v is child][0] if child else ''
        if not self._parent:
            return childname
        return (self._parent._get_fqname(self) + childname).strip('.')


    def __getitem__(self, index):
        """
        Get group or variable with the given index.
        """
        return self._cfg_get(index)._value


    def __setitem__(self, index, value):
        """
        Access group or variable with the given index.
        """
        self._cfg_get(index)._cfg_set(value)


    def __nonzero__(self):
        """
        Return False if there are no elements in the dict.
        """
        return len(self) > 0


    def __len__(self):
        """
        Returns number of items in the dict.
        """
        return len(list(self._vars()))


    def _hash(self, values=True):
        """
        Returns a hash of the config item.
        """
        hash = hashlib.md5(super(Container, self)._hash(values))
        for name, var in self._vars():
            hash.update(repr(name) + var._hash(values))
        return hash.hexdigest()


    def _stringify(self, print_desc=True):
        """
        Convert object into a string to write into a config file.
        """
        ret = []
        fqn = self._get_fqname()
        if print_desc:
            sections = [x.capitalize() for x in fqn.split('.')]
            breadcrumb = ' > '.join(sections)
            ret.append('#\n# Begin %s: %s\n#' % (self.__class__.__name__, breadcrumb))

        if print_desc:
            # TODO: more detailed comments, show full spec of var and some examples.
            ret.append('# | %s' % fqn)
            if self._desc:
                desc = unicode_to_str(self._desc).replace('\n', '\n# | ')
                ret.append('# |\n# | %s' % desc)

        var_strings = []
        space_vars = False
        for name, var in self._vars():
            cfgstr = var._stringify(False).lstrip('\n')

            if isinstance(self, List):
                # Replace explicit indexes with implicit indexing tokens.
                # [+] means append, while [ ] references last element.
                # FIXME: this logic belongs in the List class instead, but will
                # require some refactoring first.
                def replace(m):
                    ret = fqn + ('[+]' if replace.first else '[ ]')
                    replace.first = False
                    return ret
                replace.first = True
                cfgstr = re.sub(re.compile('^%s\[\d+\]' % re.escape(fqn), re.M), replace, cfgstr)

            var_strings.append(cfgstr)
            if '\n' in cfgstr:
                space_vars = True

        for cfgstr in var_strings:
            if '# Begin' in cfgstr and (not ret or not ret[-1].endswith('\n')):
                # Config item is a group or list, space it down with a blank
                # line for readability.
                ret.append('')
            ret.append(cfgstr)
            if space_vars:
                # Separate multi-line subgroups with newline.
                ret.append('')

        if print_desc:
            ret.append('#\n# End %s: %s\n#' % (self.__class__.__name__, breadcrumb))
        return '\n'.join(ret)


    def _coerce_key(self, key):
        """
        Given the key, return a type appropriate for the container, or raise
        ValueError otherwise.
        """
        if isinstance(key, self._type):
            return key

        if self._type == str:
             return unicode_to_str(key)
        elif self._type == unicode:
            return str_to_unicode(key)
        else:
            # this will raise if key can't be coerced to _type.
            return self._type(key)


    def _cfg_get(self, key, create=True):
        """
        Get group or variable with the given key (as object, not value).
        """
        key = self._coerce_key(key)
        try:
            return self._real_cfg_get(key)
        except (KeyError, IndexError):
            if not create:
                raise
            newitem = self._schema.copy()
            newitem._parent = self
            if isinstance(newitem, Group):
                for item in newitem._schema:
                    item._parent = newitem
            elif isinstance(newitem, Dict):
                newitem._schema._parent = newitem

            self._cfg_set_item(key, newitem)
            return newitem


class Dict(Container):
    """
    A config dict.
    """
    def __init__(self, schema, desc=u'', name='', type=unicode, defaults={}):
        self._dict = {}
        super(Dict, self).__init__(name, desc, schema, type, defaults.items())


    # These methods are required by Container superclass

    def _vars(self):
        return self._dict.items()

    def _real_cfg_get(self, key):
        return self._dict[key]

    def _cfg_set_item(self, key, var):
        self._dict[key] = var


    # Methods needed to simulate dict behaviour

    def __iter__(self):
        """
        Iterate through keys.
        """
        return self.keys().__iter__()

    def __repr__(self):
        return repr(self._dict)

    def __delitem__(self, key):
        # Set to DELETED before actually deleting to notify any monitors.
        self._dict[key]._cfg_set(DELETED)
        del self._dict[key]

    def _cfg_set(self, dict):
        if isinstance(dict, Dist):
            dict = dict._dict

        if self._dict is not dict:
            self._dict.clear()
            for key, val in dict.items():
                self[key] = val


    def keys(self):
        """
        Return the keys (sorted by name)
        """
        return sorted(self._dict.keys())


    def items(self):
        """
        Return key,value list (sorted by key name)
        """
        return [ (key, self._dict[key]._value) for key in self.keys() ]


    def values(self):
        """
        Return value list (sorted by key name)
        """
        return [ self._dict[key]._value for key in self.keys() ]


    def get(self, index, default=None):
        """
        Get group or variable with the given index. Return None if it does
        not exist.
        """
        try:
            return self._cfg_get(index, False)._value
        except KeyError:
            return default



class List(Container):
    """
    A config list.
    """
    def __init__(self, schema, desc=u'', name='', defaults=[]):
        self._list = []
        if isinstance(defaults, dict):
            # Take values from dictionary sorted by keys.
            defaults = [defaults[key] for key in sorted(defaults.keys())]
        super(List, self).__init__(name, desc, schema, int, enumerate(defaults))


    # These methods are required by Container superclass

    def _vars(self):
        return enumerate(self._list)

    def _real_cfg_get(self, key):
        if self._list[key] is None:
            # Item exists but is None, so force creation of new Var object at this index
            raise IndexError
        return self._list[key]

    def _cfg_set_item(self, key, var):
        if key == len(self._list):
            self._list.append(var)
        else:
            self._list[key] = var


    # Methods needed to simulate lits behaviour

    def __iter__(self):
        """
        Iterate through values.
        """
        for var in self._list:
            yield var._value

    def __iadd__(self, l):
        self.extend(l)
        return self

    def __add__(self, l):
        new = self.copy()
        new.extend(l)
        return new

    def __eq__(self, l):
        l = l._list if isinstance(l, List) else l
        return self._list == l


    def __repr__(self):
        return repr(self._list)

    def __delitem__(self, idx):
        # Set to DELETED before actually deleting to notify any monitors.
        self._list[idx]._cfg_set(DELETED)
        del self._list[idx]

    def _cfg_set(self, l):
        l = l._list if isinstance(l, List) else l
        if self._list is not l:
            del self._list[:]
            for n, val in enumerate(l):
                self[n] = val

    def append(self, val):
        self[len(self)] = val

    def extend(self, vals):
        vals = vals._list if isinstance(vals, List) else vals
        for val in vals:
            self.append(val)

    def insert(self, idx, val):
        self._list.insert(idx, None)
        self[idx] = val

    def remove(self, val):
        for n, var in enumerate(self._list[:]):
            if var._value == val:
                del self[n]
                break
        else:
            raise ValueError('list.remove(x): x not in list')

    def pop(self, idx):
        var = self._list.pop(idx)
        return var._value


class Config(Group):
    """
    A config object. This is a group with functions to load and save a file.
    """
    def __init__(self, schema, desc=u'', name='', module = None):
        super(Config, self).__init__(schema, desc, name)
        self._filename = None
        self._bad_lines = []
        self._loaded_hash_values = None   # hash for schema + values
        self._loaded_hash_schema = None   # hash for schema only
        self._module = module

        # Whether or not to autosave config file when options have changed
        self._autosave = None
        self._autosave_timer = WeakOneShotTimer(self.save)
        self.autosave = True

        # If we are watching the config file for changes.
        self._watching = False
        self._watch_mtime = 0
        self._watch_timer = WeakTimer(self._check_file_changed)
        self._inotify = None

    def __repr__(self):
        # This is a bit of a hack: if we're being deepcopied (via copy()),
        # we recreate the _autosave_timer and _watch_timer timers.  Callable
        # calls str() on the passed callable, which implicitly calls str() on
        # the instance if you pass a method.  Group objects implement __repr__
        # which calls repr() recursively on all its config values.  With
        # deepcopy, it happens that some of our children have not yet had their
        # state restored, so repr() fails (because e.g.  _list or _dict
        # attributes don't exist yet).  So, if _autosave_timer isn't set, it
        # means we are in the midst of restoring state from a deepcopy, and in
        # that case, use the standard object __repr__.
        if not hasattr(self, '_autosave_timer'):
            return super(Base, self).__repr__()
        return super(Config, self).__repr__()

    def _hash(self, values=True):
        """
        Returns a hash of the config item.
        """
        return hashlib.md5(super(Config, self)._hash(values) + repr(self._bad_lines)).hexdigest()


    def __getstate__(self):
        state = super(Config, self).__getstate__()
        # Reset filename so we don't clobber the original config object's file.
        state['_filename'] = state['_inotify'] = None
        del state['_watch_timer'], state['_autosave_timer']
        return state


    def __setstate__(self, state):
        self.__dict__.update(state)
        # Recreate timers for new object.  See __repr__ hack above.
        self._watch_timer = WeakTimer(self._check_file_changed)
        self._autosave_timer = WeakOneShotTimer(self.save)


    def save(self, filename=None, force=False):
        """
        Save configuration file.

        :param filename: the name of the file to save; if None specified, will
                         use the name of the previously loaded file, or the
                         value assigned to the filename property.
        :param force: if False (default), will only write the file if there were
                      any changes (to either values or the schema).
        :type force: bool
        """
        if not filename:
            if not self._filename:
                raise ValueError, "Filename not specified and no default filename set."
            filename = self._filename

        # If this callback was added due to autosave, remove it now.
        main.signals['exit'].disconnect(self.save)

        hash_values = self._hash(values=True)
        if self._loaded_hash_values == hash_values and not force and filename == self._filename:
            # Nothing has changed, and forced save not required.
            return True

        filename = os.path.expanduser(filename)
        if os.path.dirname(filename) and not os.path.isdir(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename))

        self._loaded_hash_schema = self._hash(values=False)
        self._loaded_hash_values = hash_values

        self._autosave_timer.stop()
        f = open(filename + '~', 'w')
        encoding = get_encoding().lower().replace('iso8859', 'iso-8859')
        f.write('# -*- coding: %s -*-\n' % encoding + \
                '# -*- hash: %s -*-\n' % self._loaded_hash_schema)
        if self._module:
            f.write('# -*- module: %s -*-\n' % self._module)
        f.write('# *************************************************************\n'
                '# WARNING: This file is auto-generated.  You are free to edit\n'
                '# this file to change config values, but any other changes\n'
                # FIXME: custom comments lost, would be nice if they were kept.  Might
                # be tricky to fix.
                '# (including removing or rearranging lines, or adding custom\n'
                '# comments) will be lost.\n'
                '#\n'
                '# The available settings are commented out with their default\n'
                '# values.\n'
                '# *************************************************************\n')
        if self._bad_lines:
            f.write('\n# =========================================================\n'
                    '# CAUTION: This file contains syntax errors or unsupported\n'
                    '# config settings, which were ignored.  Refer to the end of\n'
                    '# this file for the relevant lines.\n'
                    '# =========================================================\n')
        f.write(self._stringify() + '\n')
        if self._bad_lines:
            f.write('\n\n\n'
                    '# *************************************************************\n'
                    '# The following lines caused errors and were ignored.  Possible\n'
                    '# reasons are removed variables or bad configuration.\n'
                    '# *************************************************************\n\n')
            for error, line in self._bad_lines:
                f.write('# %s\n%s\n\n' % (error, line))
        os.fdatasync(f.fileno())
        f.close()
        os.rename(filename + '~', filename)


    def load(self, filename=None, sync=False):
        """
        Load values from a config file previously saved for this schema.

        :param filename: filename to load values from; if None, will use the
                          :attr:`~kaa.config.Config.filename` property.
        :type filename: str
        :param sync: if True, will overwrite the current file (retaining previous
                     values, of course) if the schema has changed, or create the
                     config file if it does not exist.  (Default: False)
        :type sync: bool

        If no filename has been previously set with the :attr:`~kaa.config.Config.filename`
        property then the ``filename`` argument is required, and in that case the
        filename property will be set to this value.
        """
        local_encoding = get_encoding()
        if filename:
            filename = os.path.expanduser(filename)
        if not filename:
            if not self._filename:
                raise ValueError("Filename not specified and no default filename set.")
            filename = self._filename
        if not self._filename:
            self._filename = filename

        # if list, path -> (lastidx, maxidx); if dict, path -> keys
        container_indexes = {}
        def get_container_index_by_path(obj, path, idx):
            path = tuple(path)
            if isinstance(obj, Dict):
                # Container is a dictionary, so just remember key.
                container_indexes.setdefault(path, set()).add(idx[1:-1])
                return idx

            # It's a list.
            if path not in container_indexes:
                container_indexes[path] = -1, -1
            if idx == '[+]':
                nextidx = container_indexes[path][1] + 1
                container_indexes[path] = nextidx, nextidx
            elif idx != '[ ]':
                # FIXME: validate explicit idx
                idx = int(idx[1:-1])
                container_indexes[path] = idx, max(idx, container_indexes[path][1])
            return '[%d]' % container_indexes[path][0]

        def get_object_by_path(path):
            obj = self
            # Given a.b.c.d, fetch up to c, so obj=c
            for idx, key in enumerate(path):
                if key.startswith('['):
                    key = keylist[idx] = get_container_index_by_path(obj, keylist[:idx], key)
                    obj = obj[key[1:-1]]
                else:
                    obj = getattr(obj, key)
            return obj

        line_regexp = re.compile('^([a-zA-Z0-9_-]+|\[.*?\]|\.)+ *= *(.*)')
        key_regexp = re.compile('(([a-zA-Z0-9_-]+)|(\[.*?\]))')

        self._loaded_hash_schema = None
        self._loaded_hash_value = None

        if not os.path.isfile(filename):
            # filename not found
            if sync:
                self.save(filename)
            return False

        # Disable autosaving while we load the config file.
        autosave_orig = self.autosave
        self.autosave = False

        f = open(filename)
        for line in f.readlines():
            line = line.strip()
            if line.startswith('# -*- coding:'):
                # a encoding is set in the config file, use it
                try:
                    encoding = line[14:-4]
                    ''.encode(encoding)
                    local_encoding = encoding
                except UnicodeError:
                    # bad encoding, ignore it
                    pass
            elif line.startswith('# -*- hash:'):
                self._loaded_hash_schema = line[12:].rstrip('-* ')

            # convert lines based on local encoding
            line = unicode(line, local_encoding)
            if line.find('#') >= 0:
                line = line[:line.find('#')]
            line = line.strip()
            if not line:
                continue

            # split line in key = value
            m = line_regexp.match(line.strip())
            if not m:
                error = ('Unable to parse the line', line.encode(local_encoding))
                if not error in self._bad_lines:
                    log.warning('%s: %s' % error)
                    self._bad_lines.append(error)
                continue
            value = m.groups()[1]
            if value:
                key = line[:-len(value)].rstrip(' =')
            else:
                key = line.rstrip(' =')

            try:
                keylist = [x[0] for x in key_regexp.findall(key.strip()) if x[0]]
                # Given a.b.c.d, set obj to a.b.c
                obj = get_object_by_path(keylist[:-1])
                key, value = keylist[-1], value.strip()

                if '<default: ' in value and value.endswith('>'):
                    if value.startswith('<default: '):
                        # Set the Var to the default value.  We do this explicitly
                        # in case we are _re_loading a config and the var has
                        # reverted to default.
                        value = DEFAULT
                    else:
                        # User has modified the value but not removed <default: ...>, e.g.:
                        #   foo.bar = myvalue <default: 42>
                        # It should be safe to strip the default stuff.
                        value = value[:value.find('<default: ')].strip()

                # Now assign the value to object.d
                if isinstance(obj, Container):
                    key = get_container_index_by_path(obj, keylist[:-1], key)
                    obj[key[1:-1]] = value
                else:
                    setattr(obj, key, value)
            except Exception, e:
                error = (str(e), line.encode(local_encoding))
                if not error in self._bad_lines:
                    log.warning('%s: %s' % error)
                    self._bad_lines.append(error)
        f.close()

        # TODO: now that we know which list indexes / dict keys have been
        # assigned in the config file (via container_indexes), we need to walk
        # the whole config tree and delete indexes/keys that weren't referenced
        # in the file.

        self.autosave = autosave_orig
        self._watch_mtime = os.stat(filename)[stat.ST_MTIME]
        if sync and self._loaded_hash_schema != self._hash(values=False):
            # Schema has changed and sync needed.  Saving will update
            # self._loaded_hash_values
            self.save(filename)
        else:
            self._loaded_hash_values = self._hash(values=True)

        return len(self._bad_lines) == 0


    @property
    def filename(self):
        """
        The current config filename.
        """
        return self._filename

    @filename.setter
    def filename(self, filename):
        self._filename = filename


    @property
    def autosave(self):
        """
        Whether or not changes are automatically save.

        If True, will write the config filename (either previously passed to
        :meth:`~kaa.config.Config.load` or defined by the
        :attr:`~kaa.config.Config.filename` property) 5 seconds after the last
        config value update (or program exit, whichever comes first).
        """
        return self._autosave


    @autosave.setter
    def autosave(self, autosave):
        if autosave and not self._autosave:
            self.add_monitor(WeakCallable(self._config_changed_cb))
        elif not autosave and self._autosave:
            self.remove_monitor(WeakCallable(self._config_changed_cb))
            self._autosave_timer.stop()
        self._autosave = autosave


    def _config_changed_cb(self, name, oldval, newval):
        if self._filename:
            if not self._autosave_timer.active:
                main.signals['exit'].connect(self.save)
            # Start/restart the timer to save in 5 seconds.
            self._autosave_timer.start(5)

    def watch(self, watch = True):
        """
        If argument is True (default), adds a watch to the config file and will
        reload the config if it changes.  If INotify is available, use that,
        otherwise stat the file every 3 seconds.

        If argument is False, disable any watches.
        """
        if watch and not self._inotify:
            try:
                self._inotify = INotify()
            except SystemError:
                pass

        assert(self._filename)
        if self._watch_mtime == 0:
            self.load()

        if not watch and self._watching:
            if self._inotify:
                self._inotify.ignore(self._filename)
            self._watch_timer.stop()
            self._watching = False

        elif watch and not self._watching:
            if self._inotify:
                try:
                    signal = self._inotify.watch(self._filename)
                    signal.connect_weak(self._file_changed)
                except IOError:
                    # Adding watch failed, use timer to wait for file to appear.
                    self._watch_timer.start(3)
            else:
                self._watch_timer.start(3)

            self._watching = True


    def _check_file_changed(self):
        try:
            mtime = os.stat(self._filename)[stat.ST_MTIME]
        except (OSError, IOError):
            # Config file not available.
            return

        if self._inotify:
            # Config file is now available, stop this timer and add INotify
            # watch.
            self.watch(False)
            self.watch()

        if mtime != self._watch_mtime:
            return self._file_changed(INotify.MODIFY, self._filename)


    def _file_changed(self, mask, path):
        if mask & INotify.MODIFY:
            # Config file changed.  Attach a monitor so we can keep track of
            # any values that actually changed.
            changed_names = []
            cb = Callable(lambda *args: changed_names.append(args[0]))
            self.add_monitor(cb)
            self.load()
            log.info('Config file %s modified; %d settings changed.' % (self._filename, len(changed_names)))
            log.debug('What changed: %s', ', '.join(changed_names) or 'nothing')
            self.remove_monitor(cb)
        elif mask & (INotify.IGNORED | INotify.MOVE_SELF):
            # File may have been replaced, check mtime now.
            WeakOneShotTimer(self._check_file_changed).start(0.1)
            # Add a slower timer in case it doesn't reappear right away.
            self._watch_timer.start(3)


def set_default(var, value):
    """
    Set default value for the given scalar config variable.
    """
    if isinstance(var, VarProxy):
        var._item._cfg_set(value, default=True)
    elif isinstance(var, Var):
        var._cfg_set(value, default=True)
    else:
        raise ValueError('Supplied config variable is not type Var or VarProxy')


def get_default(var):
    """
    Returns the default value for the given scalar config variable.
    """
    if isinstance(var, VarProxy):
        return var._item._default
    elif isinstance(var, Var):
        return var._default
    else:
        raise ValueError('Supplied config variable is not type Var or VarProxy')


def get_description(var):
    """
    Get the description for the given config variable or group.
    """
    if isinstance(var, (Group, Container)):
        return var._desc
    elif isinstance(var, VarProxy):
        return var._item._desc
    elif isinstance(var, Var):
        return var._desc
    else:
        raise ValueError('Supplied config variable is not a config variable')


def get_type(var):
    """
    Returns the type of the given config variable.

    If the config variable is a scalar, non-enumerated type, then the return
    value will be the corresponding python type (int, str, unicode, float, etc.)

    If the variable is a scalar enumerated type, the return value will be a
    tuple of possible values for that variable.

    For non-scalar types, the return value will be one of :class:`~kaa.config.List`,
    :class:`~kaa.config.Dict`, or :class:`~kaa.config.Group`.
    """
    if isinstance(var, VarProxy):
        return var._item._type
    elif isinstance(var, Var):
        return var._type
    return type(var)


def get_schema(var):
    """
    Returns the schema for a non-scalar config variable (List, Dict, or Group), or
    None for scalar variables.

    The schema is another config object (:class:`~kaa.config.Var`,
    :class:`~kaa.config.List`, :class:`~kaa.config.Dict`, or
    :class:`~kaa.config.Group).

        >>> kaa.config.get_description(cfg.movies)
        u'Your favorite movies.'
        >>> schema = kaa.config.get_schema(cfg.movies)
        >>> kaa.config.get_description(schema)
        u'A movie name.'
        >>> kaa.config.get_type(schema)
        <type 'str'>
    """
    try:
        return var._schema
    except AttributeError:
        return



def get_config(filename, module = None):
    """
    Returns a Config object representing the config file provided in
    'filenane'.  If module is None, the specified config file must have the
    module specified (in the "-*- module: ... -*-" metadata), otherwise the
    supplied module (string) is used.  The module must be importable.

    If the config module cannot be determined and one is not specified,
    will raise ValueError.  If import fails, will raise ImportError.
    Otherwise will return the Config object.
    """
    filename = os.path.expanduser(filename)

    if not module:
        # No module specified, check the config file.
        metadata = file(filename).read(256)
        m = re.search(r'^# -\*- module: (\S+) -\*-$', metadata, re.M)
        if m:
            module = m.group(1)
        else:
            raise ValueError, 'No module specified in config file'

    components = module.split('.')
    attr = components.pop()
    module = '.'.join(components)
    try:
        exec('import %s as module' % module)
    except Exception, e:
        log.exception('config loader')
        raise ImportError, 'Could not import config module %s' % module

    config = getattr(module, attr)
    if config._filename and os.path.realpath(config._filename) != os.path.realpath(filename):
        # Existing config object represents a different config file,
        # so must copy.
        config = config.copy()

    config.load(filename)
    return config

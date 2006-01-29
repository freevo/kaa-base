# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# config.py - config file reader
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# Copyright (C) 2005 Dirk Meyer, Jason Tackaberry
#
# First Edition: Dirk Meyer <dmeyer@tzi.de>
# Maintainer:    Dirk Meyer <dmeyer@tzi.de>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MER-
# CHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA
#
# -----------------------------------------------------------------------------

__all__ = [ "Var", "Group", "Dict", "List", "Config" ]

# Python imports
import os
import re
import copy
import logging
from new import classobj

# kaa.base modules
from strutils import str_to_unicode, unicode_to_str, get_encoding
from kaa.notifier import Callback

# get logging object
log = logging.getLogger('config')

# align regexp
align = re.compile(u'\n *', re.MULTILINE)


class NoCopyCallback(object):
    """
    Wraps a callable and returns None for deep copies, because deepcopy
    has kittens when it runs into a callable.
    """
    def __init__(self, callback):
        self.callback = callback

    def __deepcopy__(self, memo):
        return None


def _format(text):
    """
    Format a description with multiple lines.
    """
    if text.find('\n') == -1:
        return text
    
    # description with more than one line, format the text
    if not text.startswith(u'\n'):
        # add newline at the beginning for regexp
        text = u'\n' + text
    # align desc
    strip = 100
    for m in align.findall(text, re.MULTILINE):
        strip = min(len(m), strip)
    if strip == 100 or strip < 2:
        # nothing found
        return text

    newtext = []
    for line in text.split(u'\n'):
        newtext.append(line[strip-1:])
    return u'\n'.join(newtext)[1:]


class Base(object):
    """
    Base class for all config objects.
    """

    def __init__(self, name='', desc=u'', default=None):
        self._parent = None
        self._name = name
        self._desc = _format(str_to_unicode(desc))
        self._default = default
        self._value = default
        self._monitors = []

    def copy(self):
        """
        Return a deep copy of the object.
        """
        return copy.deepcopy(self)

    def add_monitor(self, callback):
        assert(callable(callback))
        # Wrap the function or method in a class that will ignore deep copies
        # because deepcopy() is unable to copy callables.
        callback = NoCopyCallback(callback)
        self._monitors.append(callback)

    def remove_monitor(self, callback):
        for monitor in self._monitors:
            if callback == monitor.callback:
                self._monitors.remove(monitor)

    def _notify_monitors(self, oldval):
        names = []
        o = self
        while o:
            if o._name:
                if names and names[0][0] == "[":
                    # List/dict index, just concat to previous name.
                    names[0] = o._name + names[0]
                else:
                    names.insert(0, o._name)

            for monitor in o._monitors:
                if names:
                    name = ".".join(names)
                else:
                    name = None
                monitor.callback(name, oldval, self._value)
            o = o._parent

    def get_parent(self):
        return self._parent


class VarProxy(Base):
    """
    Wraps a config variable value, inheriting the actual type of that
    value (int, str, unicode, etc.) and offers add_monitor and remove_monitor
    methods to manage the monitor list of the original Var object.
    """
    def __new__(cls, value = None, monitors = [], parent = None):
        clstype = realclass = type(value)
        if clstype == bool:
            # You can't subclass a boolean, so use int instead.  In practice,
            # this isn't a problem, since __class__ will end up being bool,
            # thanks to __getattribute__, so isinstance(o, bool) will be True.
            clstype = int
        newclass = classobj("VarProxy", (clstype, cls), {
            "__getattribute__": cls.__getattribute__,
            "__str__": cls.__str__,
        })
        if value:
            self = newclass(value)
        else:
            self = newclass()
        self._class = realclass
        return self


    def __init__(self, value = None, monitors = [], parent = None):
        super(Base, self).__init__(default = value)
        self._monitors = monitors
        self._parent = parent

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


    def _cfg_string(self, prefix, print_desc=True):
        """
        Convert object into a string to write into a config file.
        """
        if not prefix.endswith(']'):
            # add name if the prefix is not a dict
            prefix = prefix + self._name

        # create description
        desc = newline = ''
        if print_desc:
            desc = '# %s\n' % unicode_to_str(self._desc).replace('\n', '\n# ')
            newline = '\n'
        # convert value to string
        value = unicode_to_str(self._value)
        if self._value == self._default:
            # print default value
            return '%s# %s = %s%s' % (desc, prefix, value, newline)
        # print current value
        return '%s%s = %s%s' % (desc, unicode_to_str(prefix), value, newline)


    def _cfg_set(self, value, default=False):
        """
        Set variable to value. If the type is not right, an expection will
        be raised. The function will convert between string and unicode.
        If default is set to True, the default value will also be changed.
        """
        if isinstance(self._type, (list, tuple)):
            if not value in self._type:
                # This could crash, but that is ok
                value = self._type[0].__class__(value)
            if not value in self._type:
                raise AttributeError('Variable must be one of %s' % str(self._type))
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
            oldval = self._value
            self._value = value
            self._notify_monitors(oldval)
        return value

        
class Group(Base):
    """
    A config group.
    """
    def __init__(self, schema, desc=u'', name=''):
        super(Group, self).__init__(name, desc)
        self._dict = {}
        self._vars = []
        self._schema = schema

        for data in schema:
            if not data._name:
                raise AttributeError('no name given')
            self._dict[data._name] = data
            self._vars.append(data._name)

        # the value of a group is the group itself
        self._value = self

        # Parent all the items in the schema
        for item in schema:
            item._parent = self


    def add_variable(self, name, value):
        """
        Add a variable to the group. The name will be set into the
        given value. The object will _not_ be copied.
        """
        value._name = name
        value._parent = self
        self._dict[name] = value
        self._vars.append(name)


    def _cfg_string(self, prefix, print_desc=True):
        """
        Convert object into a string to write into a config file.
        """
        ret  = []
        desc = unicode_to_str(self._desc).replace('\n', '\n# ')
        if self._name:
            # add self._name to prefix and add a '.'
            prefix = prefix + self._name + '.'
        if prefix and not prefix.endswith('].') and print_desc:
            # print description for 'stand alone' groups
            ret.append('#\n# %s\n# %s\n#\n' % (prefix[:-1], desc))
        for name in self._vars:
            var = self._dict[name]
            ret.append(var._cfg_string(unicode_to_str(prefix), print_desc))
        return '\n'.join(ret)


    def _cfg_get(self, key):
        """
        Get variable, subgroup, dict or list object (as object not value).
        """
        if not key in self._dict:
            raise AttributeError('No attribute %s' % key)
        return self._dict[key]


    def __setattr__(self, key, value):
        """
        Set a variable in the group.
        """
        if key.startswith('_'):
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
            return VarProxy(item._value, item._monitors, item._parent)

        return item



class Dict(Base):
    """
    A config dict.
    """
    def __init__(self, schema, desc=u'', name='', type=unicode):
        super(Dict, self).__init__(name, desc)
        self._schema = schema
        self._dict = {}
        self._type = type
        # the value of a dict is the dict itself
        self._value = self
        schema._parent = self


    def keys(self):
        """
        Return the keys (sorted by name)
        """
        keys = self._dict.keys()[:]
        keys.sort()
        return keys


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


    def _cfg_string(self, prefix, print_desc=True):
        """
        Convert object into a string to write into a config file.
        """
        ret = []
        prefix = prefix + self._name
        if type(self._schema) == Var and print_desc:
            ret.append('#\n# %s\n# %s\n#\n' % (prefix, unicode_to_str(self._desc)))
            print_desc = False

        for key in self.keys():
            # get the var before we might change the key to string
            var = self._dict[key]
            # convert key to string
            if isinstance(key, unicode):
                key = unicode_to_str(key)
            # create new prefix. The prefix is the old one + [key] and
            # if the next item is not a Var, add a '.'
            new_prefix = '%s' % (prefix)
            if not isinstance(self._schema, Var):
                new_prefix += '.'
            ret.append(var._cfg_string(new_prefix, print_desc))
        if not print_desc:
            ret.append('')
        return '\n'.join(ret)


    def _cfg_get(self, index, create=True):
        """
        Get group or variable with the given index (as object, not value).
        """
        if not isinstance(index, self._type):
            if self._type == str:
                index = unicode_to_str(index)
            elif self._type == unicode:
                index = str_to_unicode(index)
            else:
                # this could crash, we don't care.
                index = self._type(index)
        if not index in self._dict and create:
            newitem = self._dict[index] = self._schema.copy()
            newitem._parent = self
            newitem._name = u"[%s]" % unicode(index)
            if isinstance(newitem, Group):
                for item in newitem._schema:
                    item._parent = newitem
            elif isinstance(newitem, Dict):
                newitem._schema._parent = newitem

        return self._dict[index]


    def get(self, index):
        """
        Get group or variable with the given index. Return None if it does
        not exist.
        """
        try:
            return self._cfg_get(index, False)._value
        except KeyError:
            return None

        
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


    def __iter__(self):
        """
        Iterate through keys.
        """
        return self.keys().__iter__()


    def __nonzero__(self):
        """
        Return False if there are no elements in the dict.
        """
        return len(self._dict.keys()) > 0

    
class List(Dict):
    """
    A config list. A list is only a dict with integers as index.
    """
    def __init__(self, schema, desc=u'', name=''):
        Dict.__init__(self, schema, desc, name, int)


    def __iter__(self):
        """
        Iterate through values.
        """
        return self.values().__iter__()


class Config(Group):
    """
    A config object. This is a group with functions to load and save a file.
    """
    def __init__(self, schema, desc=u'', name=''):
        Group.__init__(self, schema, desc, name)
        self._filename = ''
        self._bad_lines = []


    def save(self, filename=''):
        """
        Save file. If filename is not given use filename from last load.
        """
        if not filename:
            filename = self._filename
        if not filename:
            raise AttributeError('no file to save to')

        if os.path.dirname(filename) and not os.path.isdir(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename))

        f = open(filename, 'w')
        f.write('# -*- coding: %s -*-\n' % get_encoding().lower())
        f.write('# *************************************************************\n')
        f.write('# This file is auto-generated\n#\n')
        f.write('# The possible variables are commented out with the default\n')
        f.write('# values. Removing lines has no effect, they will be added\n')
        f.write('# again when this file is saved again. Changing the order of\n')
        f.write('# the items will also be changed back on the next write.\n')
        if self._bad_lines:
            f.write('#\n# See the end of the file for bad lines ignored when the file\n')
            f.write('# was last saved.\n')
        f.write('# *************************************************************\n\n')
        f.write(self._cfg_string(''))
        if self._bad_lines:
            f.write('\n\n\n')
            f.write('# *************************************************************\n')
            f.write('# The following lines caused some errors and were ignored\n')
            f.write('# Possible reasons are removed variables or bad configuration\n')
            f.write('# *************************************************************\n\n')
            for error in self._bad_lines:
                f.write('# %s\n%s\n\n' % error)
        f.close()


    def load(self, filename):
        """
        Load config from a config file.
        """
        local_encoding = get_encoding()
        self._filename = filename
        line_regexp = re.compile('^([a-zA-Z0-9_]+|\[.*?\]|\.)+ *= *(.*)')
        key_regexp = re.compile('(([a-zA-Z0-9_]+)|(\[.*?\]))')
        if not os.path.isfile(filename):
            # filename not found
            return False
        f = open(filename)
        for line in f.readlines():
            line = line.strip()
            if line.startswith('# -*- coding:'):
                # a encoding is set in the config file, use it
                try:
                    encoding = line[14:-4]
                    ''.encode(encoding)
                    local_encoding = encoding
                except:
                    # bad encoding, ignore it
                    pass
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
                keylist = [x[0] for x in key_regexp.findall(key.strip()) if x[0] ]
                object = self
                while len(keylist) > 1:
                    key = keylist.pop(0)
                    if key.startswith('['):
                        object = object[key[1:-1]]
                    else:
                        object = getattr(object, key)
                key = keylist[0]
                value = value.strip()
                if isinstance(object, (Dict, List)):
                    object[key[1:-1]] = value
                else:
                    setattr(object, key, value)
            except Exception, e:
                error = (str(e), line.encode(local_encoding))
                if not error in self._bad_lines:
                    log.warning('%s: %s' % error)
                    self._bad_lines.append(error)
        f.close()
        return len(self._bad_lines) == 0


    def get_filename(self):
        """
        Return the current used filename.
        """
        return self._filename

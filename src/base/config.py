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
import locale
import logging

# find the correct encoding
try:
    ENCODING = locale.getdefaultlocale()[1]
    ''.encode(ENCODING)
except:
    ENCODING = 'latin-1'

# get logging object
log = logging.getLogger('config')


def _convert(string, type):
    """
    Convert str to unicode or the other way around. Do nothing if the
    string is already correct.
    """
    if type == str and isinstance(string, unicode):
        return string.encode(ENCODING, 'replace')
    if type == unicode and isinstance(string, str):
        return unicode(string, ENCODING, 'replace')
    return string


class Var(object):
    """
    A config variable.
    """
    def __init__(self, name='', type='', desc=u'', default=None):
        self._name = name
        self._type = type
        self._desc = _convert(desc, unicode)
        self._default = default
        self._value = default
        if type == '':
            # create type based on default
            if default == None:
                raise AttributeError('define type or default')
            self._type = default.__class__


    def copy(self):
        """
        Return a deep copy of the object.
        """
        return copy.deepcopy(self)


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
            desc = '# %s\n' % _convert(self._desc, str).replace('\n', '\n# ')
            newline = '\n'
        # convert value to string
        value = _convert(self._value, str)
        if self._value == self._default:
            # print default value
            return '%s# %s = %s%s' % (desc, prefix, value, newline)
        # print current value
        return '%s%s = %s%s' % (desc, prefix, value, newline)


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
            if self._type in (str, unicode):
                value = _convert(value, self._type)
            if self._type == bool:
                if not value or value.lower() in ('0', 'false', 'no'):
                    value = False
                else:
                    value = True
            else:
                # This could crash, but that is ok
                value = self._type(value)
        if default:
            self._default = value
        self._value = value
        return value

        
class Group(object):
    """
    A config group.
    """
    def __init__(self, schema, desc=u'', name=''):
        self._dict = {}
        self._vars = []
        self._desc = _convert(desc, unicode)
        self._name = name
        for data in schema:
            if not data._name:
                raise AttributeError('no name given')
            self._dict[data._name] = data
            self._vars.append(data._name)
        # the value of a group is the group itself
        self._value = self


    def add_variable(self, name, value):
        """
        Add a variable to the group. The name will be set into the
        given value. The object will _not_ be copied.
        """
        value._name = name
        self._dict[name] = value
        self._vars.append(name)


    def copy(self):
        """
        Return a deep copy of the object.
        """
        return copy.deepcopy(self)


    def _cfg_string(self, prefix, print_desc=True):
        """
        Convert object into a string to write into a config file.
        """
        ret  = []
        desc = _convert(self._desc, str).replace('\n', '\n# ')
        if self._name:
            # add self._name to prefix and add a '.'
            prefix = prefix + self._name + '.'
        if prefix and not prefix.endswith('].') and print_desc:
            # print description for 'stand alone' groups
            ret.append('#\n# %s\n# %s\n#\n' % (prefix[:-1], desc))
        for name in self._vars:
            var = self._dict[name]
            ret.append(var._cfg_string(prefix, print_desc))
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
        return self._cfg_get(key)._value



class Dict(object):
    """
    A config dict.
    """
    def __init__(self, schema, desc=u'', name='', type=unicode):
        self._schema = schema
        self._dict = {}
        self._type = type
        self._desc = _convert(desc, unicode)
        self._name = name
        # the value of a dict is the dict itself
        self._value = self


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


    def copy(self):
        """
        Return a deep copy of the object.
        """
        return copy.deepcopy(self)


    def _cfg_string(self, prefix, print_desc=True):
        """
        Convert object into a string to write into a config file.
        """
        ret = []
        prefix = prefix + self._name
        if type(self._schema) == Var and print_desc:
            ret.append('#\n# %s\n# %s\n#\n' % (prefix, _convert(self._desc, str)))
            print_desc = False

        for key in self.keys():
            # get the var before we might change the key to string
            var = self._dict[key]
            # convert key to string
            if isinstance(key, unicode):
                key = _convert(key, str)
            # create new prefix. The prefix is the old one + [key] and
            # if the next item is not a Var, add a '.'
            new_prefix = '%s[%s]' % (prefix, key)
            if not isinstance(self._schema, Var):
                new_prefix += '.'
            ret.append(var._cfg_string(new_prefix, print_desc))
        if not print_desc:
            ret.append('')
        return '\n'.join(ret)


    def _cfg_get(self, index):
        """
        Get group or variable with the given index (as object, not value).
        """
        if not isinstance(index, self._type):
            if self._type in (unicode, str):
                index = _convert(index, self._type)
            # this could crash, we don't care.
            index = self._type(index)
        if not index in self._dict:
            self._dict[index] = self._schema.copy()
        return self._dict[index]


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
        f.write('# -*- coding: %s -*-\n' % ENCODING.lower())
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
        local_encoding = ENCODING
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

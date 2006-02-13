# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# libxml2.py - libxml2 wrapper for kaa
# -----------------------------------------------------------------------------
# $Id$
#
# This module defines an alternative python wrapper for libxml2. It depends
# on the original libxml2 wrapper to be installed, it will use the C part
# of that module.
#
# The reason for this wrapper is that the libxml2 wrapper can't handle unicode
# strings. If you provide an unicode string, you can get unicode decode errors
# and all strings from libxml2 are utf-8. This wrapper makes sure that all
# content objects and attribute values are unicode, attribute names and node
# names are string (and should be ascii).
#
# This module only defines a small subset of libxml2, mainly for parsing a
# file and for create a new tree. Deleting nodes is not supported. The
# interface is also different, see test/libxml2.py for an example.
#
# Note: The module has a memory problem because of the way libxml2 handles
# the internal memeory. If you loose the reference of the Document object, the
# whole tree gets invalid. We need to find a way to fix this.
#
# -----------------------------------------------------------------------------
# Copyright (C) 2006 Dirk Meyer, et al.
#
# First Version: Dirk Meyer <dmeyer@tzi.de>
# Maintainer:    Dirk Meyer <dmeyer@tzi.de>
#
# Please see the file AUTHORS for a complete list of authors.
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

import os
import re

try:
    import libxml2mod
except ImportError:
    print 'The libxml2 python bindings are not installed'
    print 'They are part of the libxml2 package.'
    raise ImportError('libxml2 not found')

_space_subn = re.compile(u'[ \t\n]+').subn

class XMLError(Exception):

    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg


class TreeError(XMLError):
    pass

class ParserError(XMLError):
    pass


class Node(object):
    def __init__(self, _obj=None, content=None, **attrs):
        if isinstance(_obj, (str, unicode)):
            _obj = libxml2mod.xmlNewNode(_obj)
        if type(_obj).__name__ != 'PyCObject':
            raise TypeError, 'Node needs a PyCObject argument'
        self._o = _obj
        for key, value in attrs.items():
            self.setattr(key, value)
        if content:
            self.content = content

    def __str__(self):
        return libxml2mod.serializeNode(self._o, None, 1)


    # navigation
    
    def get_parent(self):
        ret = libxml2mod.parent(self._o)
        if ret == None:
            return None
        return Node(_obj=ret)

    def get_children(self):
        ret  = []
        node = self.get_first()
        while node:
            if node.type == 'element':
                ret.append(node)
            node = node.get_next()
        return ret
    
    def get_first(self):
        ret = libxml2mod.children(self._o)
        if ret == None:
            return None
        return Node(_obj=ret)

    def get_child(self, name):
        node = self.get_first()
        while node:
            if node.name == name and node.type == 'element':
                return node
            node = node.get_next()
        return None

    def get_last(self):
        ret = libxml2mod.last(self._o)
        if ret == None:
            return None
        return Node(_obj=ret)

    def get_next(self):
        ret = libxml2mod.next(self._o)
        if ret == None:
            return None
        return Node(_obj=ret)

    def get_prev(self):
        ret = libxml2mod.prev(self._o)
        if ret == None:
            return None
        return Node(_obj=ret)

    def __iter__(self):
        return NodeIterator(self)
    
    parent = property(get_parent, None, None, "Parent node")
    children = property(get_children, None, None, "All not text children nodes")

    first = property(get_first, None, None, "First child node")
    last = property(get_last, None, None, "Last sibling node")
    next = property(get_next, None, None, "Next sibling node")
    prev = property(get_prev, None, None, "Previous sibling node")


    # content
    
    def get_content(self):
        content = unicode(libxml2mod.xmlNodeGetContent(self._o), 'utf-8')
        return _space_subn(u' ', content.strip())[0]

    def get_rawcontent(self):
        return unicode(libxml2mod.xmlNodeGetContent(self._o), 'utf-8')

    def set_content(self, content):
        if isinstance(content, unicode):
            content = content.encode('utf-8')
        if not isinstance(content, str):
            content = str(content)
        content = content.replace('&', '&amp;')
        libxml2mod.xmlNodeSetContent(self._o, content)

    def set_content_raw(self, content):
        if isinstance(content, unicode):
            content = content.encode('utf-8')
        if not isinstance(content, str):
            content = str(content)
        libxml2mod.xmlNodeSetContent(self._o, content)

    content = property(get_content, set_content, None, "Content of this node")

    # name
    
    def get_name(self):
        return libxml2mod.name(self._o)

    name = property(get_name, None, None, "Node name")

    # type
    
    def get_type(self):
        return libxml2mod.type(self._o)

    type = property(get_type, None, None, "Node type")


    # attributes
    
    def hasattr(self, name):
        ret = libxml2mod.xmlHasProp(self._o, name)
        if ret is None:
            return False
        return True


    def getattr(self, name):
        return libxml2mod.xmlGetProp(self._o, name)


    def setattr(self, name, value):
        if isinstance(value, unicode):
            value = value.encode('utf-8')
        if not isinstance(value, str):
            value = str(value)
        ret = libxml2mod.xmlSetProp(self._o, name, value)
        if ret is None:
            raise TreeError('xmlSetProp() failed')
        return Node(_obj=ret)


    def delattr(self, name):
        return libxml2mod.xmlUnsetProp(self._o, name)


    def __repr__(self):
        return "<xml.Node (%s) object at 0x%x>" % (self.name, long(id (self)))

    #
    # child adding
    #

    def add_child(self, name_or_child, content=None, **attrs):
        if isinstance(name_or_child, Node):
            ret = libxml2mod.xmlAddChild(self._o, name_or_child._o)
            if ret is None:
                raise TreeError('xmlAddChild() failed')
            return Node(_obj=ret)

        if hasattr(name_or_child, '__xml__'):
            ret = libxml2mod.xmlAddChild(self._o, name_or_child.__xml__()._o)
            if ret is None:
                raise TreeError('xmlAddChild() failed')
            return Node(_obj=ret)
            
        if content:
            if isinstance(content, unicode):
                content = content.encode('utf-8')
            if not isinstance(content, str):
                content = str(content)
            content = content.replace('&', '&amp;')
        ret = libxml2mod.xmlNewChild(self._o, None, name_or_child, content)
        if ret is None:
            raise TreeError('xmlNewChild() failed')
        for key, value in attrs.items():
            if isinstance(value, unicode):
                value = value.encode('utf-8')
            if not isinstance(value, str):
                value = str(value)
            libxml2mod.xmlSetProp(ret, key, value)
        return Node(_obj=ret)
        


class NodeIterator:
    def __init__(self, node):
        self.node = node.get_first()

    def __iter__(self):
        return self

    def next(self):
        if not self.node:
            raise StopIteration
        ret = self.node
        self.node = self.node.next
        return ret


class Document(Node):
    def __init__(self, filename=None, root=None):
        if root:
            # we always have a root element, hide it
            self._doc = Document(filename)
            if filename:
                # filename is given, load the doc and make this node
                # the node named root
                c = self._doc.get_child(root)
                if not c:
                    raise ParserError('%s has no root node %s' % (filename, root))
                self._o = c._o
                return
            # no filename given, add root node to doc
            self._o = self._doc.add_child(root)._o
            return

        # a "normal" document without special root node
        self._doc = None
        if filename:
            # load file
            self._o = libxml2mod.xmlParseFile(filename)
            if self._o is None:
                # Oops, something went wrong
                raise ParserError('xmlParseFile() failed')
        else:
            # create new doc
            self._o = libxml2mod.xmlNewDoc(None)
            if self._o is None:
                # Oops, something went wrong
                raise ParserError('xmlNewDoc() failed')

    def save(self, filename):
        if self._doc:
            # this is not real doc, it is the root node
            return self._doc.save(filename)
        # delete old file (just in case)
        if os.path.isfile(filename):
            os.unlink(filename)
        return libxml2mod.xmlSaveFormatFileEnc(filename, self._o, 'UTF-8', 1)


    def __repr__(self):
        return "<xml.Document (%s) object at 0x%x>" % (self.name, long(id (self)))


    def __del__(self):
        if not self._doc:
            # this is a real doc
            libxml2mod.xmlFreeDoc(self._o)

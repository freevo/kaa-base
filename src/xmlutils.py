# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# xmlutils.py - some classes helping dealing with xml files
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# Copyright (C) 2007 Dirk Meyer, Jason Tackaberry
#
# First Edition: Dirk Meyer <dmeyer@tzi.de>
# Maintainer:    Dirk Meyer <dmeyer@tzi.de>
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

__all__ = [ 'SaxTreeHandler' ]

# python xml import
try:
    import xml.sax
except ImportError, e:
    # Small hack before the next release. FIXME: this should be
    # removed for future versions again.
    print 'Error: detected files from previous kaa.base version!'
    print 'Please reinstall kaa by deleting all \'build\' subdirs'
    print 'for all kaa source modules and delete the kaa directory'
    print 'in the site-package directory'
    raise e

class SaxTreeHandler(xml.sax.ContentHandler):
    """
    Handler for the SAX parser. The member function 'handle' will
    be called everytime an element given on init is closed. The parameter
    is the tree with this element as root. A node can either have children
    or text content. The SaxTreeHandler is usefull for simple xml files
    found in config files and information like epg data.
    """
    class Node(object):
        """
        A node created by the SaxTreeHandler
        """
        def __init__(self, name, attr):
            self.name = name
            self.attr = attr
            self.children = []
            self.content = ''

        def getattr(self, attr):
            if self.attr.has_key(attr):
                return self.attr.get(attr)
            nodes = [ n for n in self.children if n.name == attr ]
            if len(nodes) == 1:
                return nodes[0]
            return None

        def __repr__(self):
            return '<Node %s>' % self.name

    def __init__(self, *elements):
        """
        Create handler with a list of element names.
        """
        self._elements = elements
        self._nodes = []


    def startElement(self, name, attr):
        """
        SAX callback
        """
        node = self.Node(name, attr)
        if len(self._nodes):
            self._nodes[-1].children.append(node)
        self._nodes.append(node)


    def endElement(self, name):
        """
        SAX callback
        """
        node = self._nodes.pop()
        node.content = node.content.strip()
        if name in self._elements:
            self.handle(node)
        if not self._nodes:
            self.finalize()


    def characters(self, c):
        """
        SAX callback
        """
        if len(self._nodes):
            self._nodes[-1].content += c


    def handle(self, node):
        """
        SaxTreeHandler callback for a complete node.
        """
        pass


    def finalize(self):
        """
        SaxTreeHandler callback at the end of parsing.
        """
        pass


    def parse(self, f):
        parser = xml.sax.make_parser()
        parser.setFeature(xml.sax.handler.feature_external_ges, False)
        parser.setContentHandler(self)
        parser.parse(f)

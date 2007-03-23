# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# xmlutils.py - some classes helping dealing with xml files
# -----------------------------------------------------------------------------
# $Id: decorators.py 1941 2006-10-30 09:28:15Z dmeyer $
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
import xml.sax

class SaxTreeHandler(xml.sax.ContentHandler):
    """
    Handler for the SAX parser. The memeber function 'handle' will
    be called everytime an element given on init is closed. The parameter
    is the tree with this element as root. A node can either have children
    or text content.
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
            return self.attr.get(attr)

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

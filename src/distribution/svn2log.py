# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# svn2log.py - create ChangeLog file based on svn log
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

# python imports
import sys
import os
import textwrap
import popen2
import re
import xml.sax

try:
    from xmlutils import SaxTreeHandler
except ImportError:
    from kaa.xmlutils import SaxTreeHandler
    
class Entry(object):
    def __init__(self, author, date):
        self.author = author
        self.date = date
        self.changes = []

    def write(self, writer):
        writer.write('%s  %s\n' % (self.date, self.author))
        for revision, msg, files, changed_listing in self.changes:
            if not changed_listing:
                files = textwrap.wrap(', '.join(files), width=70)
            if len(files) == 1 and len(files[0]) + len(msg) < 70:
                writer.write('\n\t* %s: %s\n' % (files[0], msg))
                continue
            for line in files:
                writer.write('\n\t* %s' % line)
            writer.write(':\n')
            for delimiter in ('o ', '- '):
                found = 0
                for l in msg.split('\n'):
                    if l.startswith(delimiter):
                        found += 1
                if found > 1:
                    p = ''
                    for l in msg.split('\n'):
                        if not l.startswith(delimiter) or not p:
                            p += l
                            continue
                        if p.startswith(delimiter):
                            p = p[len(delimiter):].lstrip()
                        writer.write('\t' + '\n\t'.join(textwrap.wrap(p)) + '\n\n')
                        p = l
                    p = p[len(delimiter):].lstrip()
                    writer.write('\t' + '\n\t'.join(textwrap.wrap(p)))
                    break
            else:
                writer.write('\t' + '\n\t'.join(textwrap.wrap(msg)))
            writer.write('\n')
        writer.write('\n')
        
class LogParser(SaxTreeHandler):

    def __init__(self, writer, prefix, user):
        SaxTreeHandler.__init__(self, 'logentry')
        prefix = '/(trunk|branches/[^/]+)(/WIP)?/(%s)' % '|'.join(prefix)
        self._prefix = re.compile(prefix)
        self._entry = None
        self._user = user
        self._writer = writer
        
    def handle(self, node):
        revision = node.getattr('revision')
        date = msg = author = ''
        files = []
        changed_listing = False
        for c in node.children:
            c.content = c.content.encode('latin-1', 'ignore')
            if c.name == 'msg':
                msg = re.subn('  ', ' ', c.content)[0]
            if c.name == 'date':
                date = c.content[:c.content.find('T')]
            if c.name == 'author':
                author = c.content
                if author in self._user:
                    author = self._user[author]
                else:
                    print 'unknown author', author
            if c.name == 'paths':
                for path in c.children:
                    if self._prefix.search(path.content):
                        f = self._prefix.sub('', path.content)
                        if not len(f):
                            f = path.content
                        if path.getattr('action') == "D":
                            files.append(f[1:] + " (removed)")
                            changed_listing = True
                        elif path.getattr('action') == "A":
                            files.append(f[1:] + " (added)")
                            changed_listing = True
                        else:
                            files.append(f[1:])
                if not len(files):
                    print 'error detecting files'
                    for path in c.children:
                        print path.content
                    print
                    
        if self._entry and (self._entry.author != author or self._entry.date != date):
            self._entry.write(self._writer)
            self._entry = None
        if not self._entry:
            self._entry = Entry(author, date)
        self._entry.changes.append((revision, msg, files, changed_listing))

    def finalize(self):
        self._entry.write(self._writer)


def svn2log(module):
    if not os.path.isfile('ChangeLog.in'):
        return
    prefix = [ module ]
    users = {}
    for line in open('ChangeLog.in'):
        if line.startswith('user'):
            login, name = line[4:].strip().split(' ', 1)
            users[login] = name
        if line.startswith('aka'):
            prefix.append(line[4:].strip())

    # Create a parser
    parser = xml.sax.make_parser()

    reader = popen2.popen2('svn log -v --xml')[0]
    writer = open('ChangeLog', 'w')

    dh = LogParser(writer, prefix, users)

    # Tell the parser to use our handler
    parser.setContentHandler(dh)

    # parse the input, add file:// so the parser will find
    # the dtd for program files.
    parser.parse(reader)

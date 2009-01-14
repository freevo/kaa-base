# No comments in here yet, because this code is repulsive.

import re
from sphinx.util.compat import make_admonition
from sphinx.ext.autodoc import prepare_docstring
import sphinx.addnodes

from docutils.parsers.rst import directives
from docutils import nodes
from docutils.statemachine import ViewList

DELIM = u'xyzzy' * 10


class kaatable(nodes.paragraph):
    pass

class kaasection(nodes.paragraph):
    pass


def get_signals(cls):
    for key, val in getattr(cls, '__kaasignals__', {}).items():
        yield key, val


def get_properties(cls):
    for name in dir(cls):
        attr =  getattr(cls, name)
        if isinstance(attr, property):
            yield name, attr


def get_methods(cls):
    for name in dir(cls):
        attr =  getattr(cls, name)
        if callable(attr) and not name.startswith('_'):
            yield name, attr


def get_first_line(docstr):
    if not docstr:
        return ''
    docstr = docstr.lstrip('\n')
    prefix = docstr[:docstr.index(docstr.strip())]
    lines = [ re.sub(r'^%s' % prefix, '', s).rstrip() for s in docstr.split('\n') ]
    if '' in lines:
        lines = lines[:lines.index('')]
    return ' '.join(lines)


def get_class(fullname):
    mod, clsname = fullname.rsplit('.', 1)
    cls = getattr(__import__(mod), clsname)
    return cls, clsname


def synopsis_directive(name, arguments, options, content, lineno,
                       content_offset, block_text, state, state_machine):
    self=state.document.settings
    list = ViewList()
    cls, clsname = get_class(arguments[0])

    table = kaatable()
    table.clsname = arguments[0]

    def add(v1, v2):
        list.append(DELIM, '')
        list.append(v1, '')
        list.append(DELIM, '')
        list.append(v2, '')
        list.append(DELIM, '')

    for key, val in get_signals(cls):
        add(key, get_first_line(val))
    add('', '')

    for name, prop in get_properties(cls):
        add(name, get_first_line(prop.__doc__))
    add('', '')

    for name, method in get_methods(cls):
        add(name, get_first_line(method.__doc__))
    add('', '')

    table.append(nodes.Text(DELIM))
    state.nested_parse(list, 0, table)
    return [table]


def kaatable_visit(self, node):
    return

def kaatable_depart(self, node):
    # This is where things get ugly.  Conceptually I'm fairly sure this entire
    # approach (of rewriting the body in the depart handler) is completely
    # wrong, but I can't figure out the proper way to do it.

    idx = self.body.index(DELIM)
    html = ''.join(self.body[idx+2:])
    del self.body[idx:]
    signals, properties, methods = [], [], []
    all = [signals, properties, methods]

    for name, desc in re.findall(r'%s(.*?)%s(.*?)%s' % (DELIM, DELIM, DELIM), html, re.S):
        if name == desc == '</p>\n<p>':
            all.pop(0)
        else:
            all[0].append((name.strip(), desc.strip()))
 
    self.body.append('<h4>Synopsis</h4>')

    link = lambda name, display: '<a title="%s.%s" class="reference internal" href="#%s.%s">%s</a>' % \
                                 (node.clsname, name, node.clsname, name, display)
    methods_filter = lambda name: link(name, name) + '()'
    properties_filter = lambda name: link(name, name)
    signals_filter = lambda name: link('signals.%s' % name, name)

    for what in ('methods', 'properties', 'signals'):
        list = locals()[what]
        filter = locals()['%s_filter' % what]
        self.body.append('<b>%s</b>' % what.title())
        if not list:
            self.body.append('<p>This class has no %s.</p>' % what)
        else:
            self.body.append('<table class="kaa %s">' % what)
            for name, desc in list:
                self.body.append('<tr><th>%s</th><td>%s</td></tr>' % (filter(name), desc))
            self.body.append('</table>')



def auto_directive(name, arguments, options, content, lineno,
                       content_offset, block_text, state, state_machine):
    self=state.document.settings
    list = ViewList()

    cls, clsname = get_class(arguments[0])
    section = kaasection()
    section.title = name[4:].title()

    if name == 'automethods':
        for attrname, method in get_methods(cls):
            list.append(u'.. automethod:: %s.%s' % (arguments[0], attrname), '')
    elif name == 'autoproperties':
        # TODO: indicate somewhere if property is read/write.
        for attrname, prop in get_properties(cls):
            list.append(u'.. autoattribute:: %s.%s' % (arguments[0], attrname), '')
    elif name == 'autosignals':
        for attrname, docstr in get_signals(cls):
            list.append(u'.. attribute:: %s' %  attrname, '')
            list.append(u'', '')
            for line in docstr.split('\n'):
                list.append(line, '')
            list.append(u'', '')

    if not len(list):
        return []

    state.nested_parse(list, 0, section)
    if name == 'autosignals':
        # For signals, rewrite the id for each attribute from kaa.Foo.bar to
        # kaa.Foo.signals.bar (to prevent conflicts from actual attributes
        # called bar).
        for child in section.children:
            if isinstance(child, sphinx.addnodes.desc) and child.children:
                signame = str(child.children[0][0].children[0])
                child.children[0]['ids'] = [u'%s.signals.%s' % (arguments[0], signame)]

    return [section]


def kaasection_visit(self, node):
    self.body.append('<h4>%s</h4>' % node.title)

def kaasection_depart(self, node):
    return

def setup(app):
    app.add_node(kaatable, html=(kaatable_visit, kaatable_depart))
    app.add_node(kaasection, html=(kaasection_visit, kaasection_depart))
    app.add_directive('autosynopsis', synopsis_directive, 1, (0, 1, 1))
    app.add_directive('automethods', auto_directive, 1, (0, 1, 1))
    app.add_directive('autoproperties', auto_directive, 1, (0, 1, 1))
    app.add_directive('autosignals', auto_directive, 1, (0, 1, 1))

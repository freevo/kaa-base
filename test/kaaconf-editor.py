#!/usr/bin/env python
#
# kaaconf-editor - GTK-based kaa.config file editor
# 
# 
#  Still TODO:
#    - Support List and Dict types
#    - Implement filter
#    - Allow specifying module to import when config file doesn't contain it
#      (also needed for creating new config files)
#    - Miscellaneous polish
#    - Code cleanup and commenting

import os
import sys

import pygtk
pygtk.require('2.0')
import gtk
import gtk.glade
import gobject

import kaa, kaa.config

# use gtk main loop
kaa.main.select_notifier('gtk')

class ProxyCellRenderer(gtk.CellRenderer):

    __gproperties__ = {
        'value' : (gobject.TYPE_PYOBJECT, None, None, gobject.PARAM_READWRITE)
        }

    __gsignals__ = {
        'changed': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_STRING, gobject.TYPE_PYOBJECT)) 
    }

    def __init__(self, widget = None):
        self.__gobject_init__()
        self._value = None
        self._text_renderer = gtk.CellRendererText()
        self._text_renderer.set_property('editable', True)
        self._text_renderer.connect('edited', self.edited_handler)

        self._toggle_renderer = gtk.CellRendererToggle()
        self._toggle_renderer.set_property('xalign', 0.0)
        self._toggle_renderer.set_property('activatable', True)

        self._combo_renderer = gtk.CellRendererCombo()
        self._combo_renderer.set_property('editable', True)
        self._combo_renderer.set_property('has-entry', False)
        self._combo_renderer.set_property('text-column', 0)
        self._combo_renderer.connect('edited', self.edited_handler)

        self._cur_renderer = None

    def do_get_property(self, property):
        if property.name == 'value':
            return self._value
        else:
            raise AttributeError, 'unknown property %s' % property.name


    def do_set_property(self, property, value):
        if property.name != 'value':
            raise AttributeError, 'unknown property %s' % property.name

        self._value = value
        if self._value[0] == 'text':
            self._cur_renderer, mode = self._text_renderer, gtk.CELL_RENDERER_MODE_EDITABLE
            self._text_renderer.set_property('text', self._value[1])
        elif self._value[0] == 'checkbox':
            self._cur_renderer, mode = self._toggle_renderer, gtk.CELL_RENDERER_MODE_ACTIVATABLE
            self._toggle_renderer.set_property('active', self._value[1])
        elif self._value[0] == 'combo':
            self._cur_renderer, mode = self._combo_renderer, gtk.CELL_RENDERER_MODE_EDITABLE
            self._combo_renderer.set_property('text', self._value[1])
            self._combo_renderer.set_property('model', self._value[2])

        self.set_property('mode', mode)


    def do_render(self, window, widget, background_area, cell_area, expose_area, flags):
        if self._value == None:
            self._text_renderer.set_property('text', '<no value>')

        return self._cur_renderer.render(window, widget, background_area, cell_area, expose_area, flags)

    def do_get_size(self, widget, cell_area):
        return self._cur_renderer.get_size(widget, cell_area)

    def do_activate(self, event, widget, path, background_area, cell_area, flags):
        if self._value[0] == 'checkbox':
            self._value[1] = not self._value[1]
            if not event:
                # When spacebar is used to toggle, event is None.  I have to
                # explicitly queue a redraw here or else it doesn't reflect the
                # toggle.  Why?
                widget.queue_draw()
            self.emit('changed', path, self._value[1])
        return True


    def do_start_editing(self, event, widget, path, background_area, cell_area, flags):
        if not event:
            # Complains when no event, so create dummy
            event = gtk.gdk.Event(gtk.gdk.NOTHING)
        self._edit_data = widget, path, self._value
        return self._cur_renderer.start_editing(event, widget, path, background_area, cell_area, flags)


    def edited_handler(self, entry, cell, text):
        tree, path, value = self._edit_data
        value[1] = text
        self.set_property('value', value)
        # Combo widget loses focus, refocus tree after edit.
        # FIXME: doesn't work when edit is cancelled
        tree.grab_focus()
        self._edit_data = None
        self.emit('changed', path, text)

gobject.type_register(ProxyCellRenderer)



class Editor(object):
    def __init__(self):
        self._current_group = None
        self._current_cfg_path = [], []
        self._filter_changed_timer = kaa.OneShotTimer(self.filter_changed_timeout_handler)

        gladefile = os.path.dirname(os.path.abspath(__file__)) + '/kaaconf-editor.glade'
        self.xml = gtk.glade.XML(gladefile, 'main')
        handlers = {
            'on_toolbar_open_clicked': self.open_handler,
            'on_toolbar_save_clicked': self.save_handler,
            'on_toolbar_quit_clicked': self.exit_handler,
            'on_main_delete_event': self.exit_handler,
            'on_entry_filter_changed': self.filter_changed_handler,
            'on_button_clear_clicked': self.button_clear_handler,
        }
        self.xml.signal_autoconnect(handlers)


        grouptree = self.xml.get_widget('tree-groups')
        grouptree.connect('row-activated', self.tree_row_activated_handler)
        grouptree.connect('cursor-changed', self.tree_cursor_changed_handler)
        treestore = gtk.TreeStore(gtk.gdk.Pixbuf, str)
        grouptree.set_model(treestore)

        col = gtk.TreeViewColumn()
        cr = gtk.CellRendererPixbuf()
        col.pack_start(cr, expand = False)
        col.add_attribute(cr, 'pixbuf', 0)

        cr = gtk.CellRendererText()
        col.pack_start(cr)
        col.add_attribute(cr, 'text', 1)
        grouptree.append_column(col)

        grouptree.set_search_column(1)

        vartree = self.xml.get_widget('tree-variables')
        vartree.connect('cursor-changed', self.list_cursor_changed_handler)
        liststore = gtk.ListStore(str, gobject.TYPE_PYOBJECT)
        vartree.set_model(liststore)
        cr = gtk.CellRendererText()
        col = gtk.TreeViewColumn('Name', cr, text = 0)
        col.set_reorderable(True)
        col.set_sort_column_id(0)
        col.set_min_width(150)
        col.set_resizable(True)
        vartree.append_column(col)

        cr = ProxyCellRenderer()
        cr.connect('changed', self.variable_changed)
        col = gtk.TreeViewColumn('Value', cr, value = 1)
        vartree.append_column(col)

        self._group_tree = grouptree
        self._var_tree = vartree


    def open(self, filename):
        try:
            config = kaa.config.get_config(filename)
        except Exception, msg:
            alert = gtk.MessageDialog(buttons = gtk.BUTTONS_CLOSE)
            alert.set_markup('<span weight="bold" size="larger">Open failed</span>\n\n%s' % msg)
            alert.run()
            alert.destroy()
            return
        
        self._config = config
        self.populate_groups()


    def populate_groups(self):
        store = self._group_tree.get_model()
        store.clear()
        pb = self.xml.get_widget('main').render_icon(gtk.STOCK_DIRECTORY, gtk.ICON_SIZE_MENU)

        def add_group(parent, group):
            for var in group.variables:
                if isinstance(getattr(group, var), kaa.config.Group):
                    node = store.append(parent, [pb, var])
                    add_group(node, getattr(group, var))

        root = store.append(None, [pb, '/'])
        add_group(root, self._config)

        self._group_tree.expand_all()
        self._group_tree.set_cursor((0,))


    def populate_variables_from_cfgpath(self):
        path = list(self._current_cfg_path[0])
        group = self._config
        while path:
            group = getattr(group, path.pop(0))

        self._current_group = group
        self._current_cfg_path = self._current_cfg_path[0], []
        store = self._var_tree.get_model()
        store.clear()
        for var in group.variables:
            proxy = getattr(group, var)
            if isinstance(proxy, kaa.config.Group):
                continue

            vartype = kaa.config.get_type(proxy)
            if isinstance(vartype, (tuple, list)):
                model = gtk.ListStore(str)
                for option in vartype:
                    model.append([option])
                store.append([var, ['combo', str(proxy), model]])
            elif vartype == bool:
                store.append([var, ['checkbox', bool(proxy)]])
            elif vartype in (kaa.config.List, kaa.config.Dict):
                store.append([var, ['text', '[Dict type not yet implemented]']])
                
            else:
                store.append([var, ['text', str(proxy)]])

        self._var_tree.columns_autosize()

    def variable_changed(self, renderer, path, value):
        model = self._var_tree.get_model()
        iter = model.get_iter(path)
        current_var_name = model.get_value(iter, 0)
        setattr(self._current_group, current_var_name, value)


    def tree_row_activated_handler(self, tree, path, column):
        if tree.row_expanded(path):
            tree.collapse_row(path)
        else:
            tree.expand_row(path, False)

    def tree_cursor_changed_handler(self, tree):
        self._current_cfg_path = self._get_current_cfg_path()
        self.populate_variables_from_cfgpath()
        self.set_info()
        self.update_status()


    def list_cursor_changed_handler(self, tree):
        self._current_cfg_path = self._get_current_cfg_path()
        self.set_info()
        self.update_status()


    def _get_current_cfg_path(self):
        path, col = self._group_tree.get_cursor()
        model = self._group_tree.get_model()
        iter = model.get_iter(path)
        parts = []
        while iter:
            next_iter = model.iter_parent(iter)
            if not next_iter:
                break

            part = model.get_value(iter, 1)
            parts.insert(0, part)
            iter = next_iter

        model = self._var_tree.get_model()
        path, col = self._var_tree.get_cursor()
        if path:
            iter = model.get_iter(path)
            return parts, [model.get_value(iter, 0)]
        return parts, []


    def set_info(self):
        if not self._current_cfg_path[1]:
            var = self._current_group
        else:
            var = getattr(self._current_group, self._current_cfg_path[1][0])

        path = self._current_cfg_path[0] + self._current_cfg_path[1]
        vartype = kaa.config.get_type(var)
        if isinstance(vartype, (tuple, list)):
            # XXX: do we want to list them?
            type_name = 'Enumerated Type'
        else:
            typemap = {
                kaa.config.Group: 'Group',
                kaa.config.Config: 'Group',
                kaa.config.List: 'List',
                kaa.config.Dict: 'Dict',
                bool: 'Boolean',
                int: 'Integer',
                str: 'String',
                unicode: 'Unicode String'
            }
            type_name = typemap.get(vartype, 'Unknown')

        default = kaa.config.get_default(var)
        if not default:
            default = '<None>'

        self.xml.get_widget('label-name').set_label('.'.join(path))
        self.xml.get_widget('label-description').set_label(kaa.config.get_description(var))
        self.xml.get_widget('label-type').set_label(type_name)
        self.xml.get_widget('label-default').set_label(str(default))
        

    def update_status(self):
        path = self._current_cfg_path[0] + self._current_cfg_path[1]
        status = self.xml.get_widget('statusbar')
        status.push(0, '.'.join(path))


    def open_handler(self, *args):
        chooser = gtk.FileChooserDialog(title = 'Select Config File', action = gtk.FILE_CHOOSER_ACTION_OPEN,
                                        buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                                   gtk.STOCK_OPEN, gtk.RESPONSE_OK))
        chooser.run()
        filename = chooser.get_filename()
        chooser.destroy()

        self.open(filename)


    def exit_handler(self, *args):
        sys.exit(0)


    def save_handler(self, *args):
        self._config.save(force = True)


    def filter_changed_handler(self, text):
        self._filter_changed_timer.start(0.5)


    def filter_changed_timeout_handler(self):
        print "Filter timeout (NYI)"
 

    def button_clear_handler(self, *args):
        self.xml.get_widget('entry-filter').set_text('')
        self._filter_changed_timer.stop()
        self.filter_changed_timeout_handler()


editor = Editor()
if len(sys.argv) > 1:
    editor.open(sys.argv[1])

kaa.main.run()


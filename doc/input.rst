.. module:: kaa.input
   :synopsis: Input plugins for stdin and LIRC

Input Plugins
=============

Stdin Key Presses
-----------------

Importing *kaa.input.stdin* plugin will add a new signal to the :ref:`global
Kaa signals dictionary <mainsignals>` called ``stdin_key_press``.  When
the first callback is connected to this signal, the terminal is put into
*non-canonical mode* which allows per-keystroke input to be available
immediately.  When the last callback is disconnected (or when the program
exits), the terminal is returned to canonical mode.

The callback receives a single string argument describing the character being
inputted.  If the character is printable (e.g. alphanumberic) then it is that
character, otherwise it is one of the following strings: *up, down, right, left
pgup, pgdn, F1 through F12, ins, del, end, home, esc, tab, enter, space,
backspace*.

For example::

    import kaa, kaa.input.stdin

    def handle_char(key):
        print 'Key pressed:', key

    kaa.signals['stdin_key_press'].connect(handle_char)
    kaa.main.run()


LIRC
----

Importing *kaa.input.lirc* plugin will add a new signal to the :ref:`global
Kaa signals dictionary <mainsignals>` called ``lirc``.  Use of this plugin
requires the pylirc module to be available.

Callbacks connected to the ``lirc`` signal will be invoked for each button
pressed, and the callback will receive as a single paramter the value of the
``config`` field for the button defined in lircrc.

Key repeats are smoothed out, such that for a key being held down, the callback
will be invoked less initially, but more frequently as the key continues to be
held, up to 10 times a second.

In order to activate the plugin, you need to call the init function:

.. autofunction:: kaa.input.lirc.init

Consider the following ``~/.lircrc``::

    begin
        remote = hdpvr
        button = Play
        prog   = freevo
        repeat = 1
        config = foobar
    end

And the Python code::

    import kaa, kaa.input.lirc

    def handle_lirc(button):
        print 'Remote control button pressed:', button

    kaa.signals['lirc'].connect(handle_lirc)
    kaa.input.lirc.init('freevo')
    kaa.main.run()

When the Play button is pressed, *handle_lirc()* will be called with the value
``foobar``.

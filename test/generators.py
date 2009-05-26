import sys
import kaa
import kaa.saxutils
import xml.sax

@kaa.coroutine()
def async():
    yield kaa.NotFinished
    yield 10

@kaa.generator()
@kaa.coroutine()
def coroutine_test():
    """
    Test with a coroutine generator. The coroutine has to raise
    GeneratorExit to be stopped. Each value yielded will be send to
    the generator.
    """
    print "Is main thread:", kaa.is_mainthread()
    yield kaa.NotFinished
    yield 1
    x = yield async()
    yield x + 1
    yield 2
    yield kaa.NotFinished
    yield 3

@kaa.coroutine()
def indirect():
    yield (yield coroutine_test())

@kaa.generator()
@kaa.threaded()
def thread_test():
    """
    Test with a generator in a thread. Each value from yield is send
    to the generator.
    """
    print "Is main thread:", kaa.is_mainthread()
    yield 1
    yield 2
    yield 3

@kaa.generator(generic=True)
@kaa.threaded()
def generic_test(generator):
    """
    Test without additional decorator defined in @generator. This adds
    the argument 'generator' to the function call. This test parses an
    XML string in a thread and the callback for each child under the
    root element will send the value to the generator.
    """
    data = '''<?xml version="1.0" encoding="UTF-8" ?>
    <test>
      <item>
        <id>1</id>
      </item>
      <item>
        <id>2</id>
      </item>
    </test>
    '''
    e = kaa.saxutils.ElementParser()
    e.handle = generator.send
    parser = xml.sax.make_parser()
    parser.setContentHandler(e)
    parser.feed(data)

@kaa.coroutine()
def main():
    for test in (coroutine_test, indirect, thread_test, generic_test):
        # we need to sync on start. If the generator returns it is not
        # done. The thread may still be running and so does the
        # coroutine. It only menas that we have at least one item
        # (which will be delayed) or none at all.
        generator = yield test()
        for r in generator:
            r = yield r
            print r
        print
    sys.exit(0)

main()
kaa.main.run()

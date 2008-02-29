import kaa

#
# This is one file not directly imported by the application
#

class FooInterface(object):

    def init_FooInterface(self):
        print 'Init FooInterface:', self.get_value()

    def get_value(self):
        # this is needed for __interface__, the real object has to
        # define it somehow
        raise NotImplementedError

    def func1(self, string):
        raise NotImplementedError

    def func2(self):
        print 'already defined'

    def func3(self):
        raise NotImplementedError

    def x(self):
        print 2

kaa.utils.add_interface(FooInterface, 'test.Foo')

class BarInterface(object):

    def is_also_foo(self):
        print isinstance(self, FooInterface)

kaa.utils.add_interface(BarInterface, 'bar')


#
# This is the application
#

class MyObject(object):

    # Note: the interfaces MUST be added up to this point or it
    # will crash even if MyObject is not created!
    __metaclass__  = kaa.utils.implements('test.Foo', 'bar')

    def __init__(self):
        print 'Init MyObject'
        self.init_FooInterface()
        
    def get_value(self):
        # required by test.Foo
        return 1

    def func1(self, string):
        print string

    def x(self):
        print 1
        super(MyObject, self).x()

p = MyObject()  # print Init FooInterface: 1
p.x()           # print 1 and 2
p.func1('x')    # --> print x
p.is_also_foo() # --> print True
p.func2()       # --> print already defined
p.func3()       # --> raise NotImplementedError

import kaa

#
# This is one file not directly imported by the application
#

class FooInterface(object):

    def __interface__(self):
        # __init__ function for interfaces, no args allowed
        # will be called after __init__ of the real class
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

kaa.add_interface(FooInterface, 'test.Foo')

class BarInterface(object):

    def is_also_foo(self):
        print isinstance(self, FooInterface)

kaa.add_interface(BarInterface, 'bar')


#
# This is the application
#

class MyObject(object):
    __metaclass__  = kaa.implements('test.Foo', 'bar')

    def get_value(self):
        # required by test.Foo
        return 1

    def func1(self, string):
        print string

p = MyObject()  # print Init FooInterface: 1
p.func1('x')    # --> print x
p.is_also_foo() # --> print True
p.func2()       # --> print already defined
p.func3()       # --> raise NotImplementedError

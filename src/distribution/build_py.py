import os
import glob
import types
import stat

import distutils.command.build_py

import xmlconfig

class build_py(distutils.command.build_py.build_py):

    kaa_compiler = {
        'cxml': xmlconfig.convert
    }

    def kaa_compile_extras(self, module, module_file, package):
        if type(package) is types.StringType:
            package = package.split('.')
        elif type(package) not in (types.ListType, types.TupleType):
            raise TypeError, \
                  "'package' must be a string (dot-separated), list, or tuple"
        ttype = os.path.splitext(module_file)[1][1:]
        outfile = self.get_module_outfile(self.build_lib, package, module)
        tmpfile = outfile[:-2] + ttype
        if os.path.isfile(outfile) and \
               os.stat(module_file)[stat.ST_MTIME] < os.stat(outfile)[stat.ST_MTIME]:
            # template up-to-date
            return
        self.copy_file(module_file, tmpfile, preserve_mode=0)
        print 'convert %s -> %s' % (tmpfile, tmpfile[:-len(ttype)] + 'py')
        self.kaa_compiler[ttype](tmpfile, tmpfile[:-len(ttype)] + 'py', '.'.join(package))
        os.unlink(tmpfile)


    def check_package (self, package, package_dir):
        if package_dir.endswith('plugins'):
            return None
        return distutils.command.build_py.build_py.check_package(self, package, package_dir)


    def build_packages (self):
        distutils.command.build_py.build_py.build_packages(self)
        for package in self.packages:
            package_dir = self.get_package_dir(package)
            for ext in self.kaa_compiler.keys():
                for f in glob.glob(os.path.join(package_dir, "*." + ext)):
                    module_file = os.path.abspath(f)
                    module = os.path.splitext(os.path.basename(f))[0]
                    self.kaa_compile_extras(module, module_file, package)

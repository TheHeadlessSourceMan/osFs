#!/usr/bin/env
# -*- coding: utf-8 -*-
"""
Run unit tests

See:
    http://pyunit.sourceforge.net/pyunit.html
"""
import typing
import unittest
import os
from osFs import OsFilesystem


__HERE__=os.path.abspath(__file__).rsplit(os.sep,1)[0]+os.sep


class Test(unittest.TestCase):
    """
    Run unit test
    """

    def setUp(self):
        pass
        
    def tearDown(self):
        pass
        
    def basic(self):
        testdir=__HERE__+'test'+os.sep+'basic'
        fs=OsFilesystem()
        d=fs.get(testdir)
        print(testdir,d.filename)
        for item in d.ls:
            print(item)

        
def testSuite():
    """
    Combine unit tests into an entire suite
    """
    testSuite = unittest.TestSuite()
    testSuite.addTest(Test("basic"))
    print(testSuite)
    return testSuite
        
        
def cmdline(args:typing.Iterable[str])->int:
    """
    Run the command line

    :param args: command line arguments (WITHOUT the filename)
    """
    """
    Run all the test suites in the standard way.
    """
    #unittest.main()
    output=None
    verbosity=2
    failfast=False
    if output is None:
        output=sys.stdout
    else:
        output=open(output,'wb')
    runner=unittest.TextTestRunner(output,verbosity=verbosity,failfast=failfast)
    runner.run(testSuite())
    return 0


if __name__=='__main__':
    import sys
    cmdline(sys.argv[1:])

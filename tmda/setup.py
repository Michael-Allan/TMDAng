
# bootstrap if we need to
try:
    import setuptools  # noqa
except ImportError:
    from ez_setup import use_setuptools
    use_setuptools()

from setuptools import find_packages, setup


classifiers = ['Development Status :: 4 - Beta',
               'Environment :: Console',
               'License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)',
               'Intended Audience :: System Administrators',
               'Natural Language :: English',
               'Operating System :: MacOS :: MacOS X',
               'Operating System :: Microsoft :: Windows',
               'Operating System :: POSIX',
               'Programming Language :: Python :: 3.4',
               'Programming Language :: Python :: Implementation :: CPython',
               'Topic :: Communications :: Email :: Filters',
               'Topic :: Internet :: Proxy Servers',
               ]

setup( author = 'Jason R. Mastaler, Kevin Goodsell, Paul Jimenez, and others'
     , author_email = 'pj@place.org'
     , classifiers = classifiers
     , description = ('The Tagged Message Delivery Agent (TMDA) is a set of '
                      'anti-spam measures, including white-listing, black-listing,'
                      'challenge-response, and tagged addresses')
     , entry_points = { 'console_scripts': [ 'aspen = aspen.server:main'
                                           , 'thrash = thrash:main'
                                           , 'fcgi_aspen = fcgi_aspen:main [fcgi]'
                                            ] }
     , name = 'TMDA'
     , packages = find_packages()
     , py_modules = []
     , url = 'http://tmda.net/'
     , version = '1.2.0'
     , zip_safe = False
     , package_data = {}
     , install_requires = []
     , extras_require = { }
      )

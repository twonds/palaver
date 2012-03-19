# Copyright (c) 2005-2008 Christopher Zorn, OGG, LLC
# See LICENSE.txt for details

from distutils.core import setup


setup(name='palaver',
      version='0.6',
      description='Palaver, a twisted multi-user chat jabber component.',
      author='Christopher Zorn',
      author_email='tofu@thetofu.com',
      url='  http://github.com/twonds/palaver',
      packages=['palaver', 'twisted.plugins', 'palaver.xmpp','palaver.test'],
      package_data={'twisted.plugins': ['twisted/plugins/palaver.py']}
      )

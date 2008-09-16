Introducing Palaver
===================

Palaver is a multi-user chat componenet for Jabber and XMPP servers.  The
intention is to support all features of XEP-0045* as well as the extended
discovery features of XEP-0128**.

Palaver is written in Python using the Twisted framework for Internet
applications.  It is licensed under the open source MIT license.

The main inspiration for writing palaver was to replace JCR mu-conference.
While mu-conference has served the community well, it's lack of maintenance
has left many searching for a replacement.

  * XEP-0045: http://www.xmpp.org/extensions/xep-0045.html
 ** XEP-0128: http://www.xmpp.org/extensions/xep-0128.html

Acknowledgements
===============

Thanks to Ralph Meijer (JID: ralphm@ik.nu) and the other twisted.words
developers. 

Requirements
============

 * Twisted Core 2.4.0 or greater
 * Twisted Words 0.5 or greater
 * a Jabber or XMPP server which supports components
   Note: that palaver and the server do not need to run on the same machine
   or share any code.

Both of these dependencies can be obtained from http://twistedmatrix.com

Installing Palaver
==================

1. Install the Dependencies

Both Twisted Core and Twisted Words should be installed or otherwise
accessible.  As with all Python module, one can use the PYTHONPATH
environment variable to reference local installs if administrator or root
access is not available or a full install is not desired.

To verify that these components are working, run Python (usually just 
"python"), and type the following:

  import twisted
  print twisted.__version__
  import twisted.words

If no errors occur, the dependencies are likely to be installed properly.

1. Install Palaver

Palaver utilizes Python's distutils build and install system.  You can
install Palaver with:

  python setup.py install

Please see the distutils documentation for more information on options.  A
commonly used option is --prefix=PATH to specify where the install should
occur (this defaults to the standard site-packages directory for Python).

2. Configure Jabber Server

There are many different jabber servers out there. You will need a jabber
server that supports 'legacy' component connection or 'jabber:component:accept'.Palaver will support other
ways, but for now it only connects via the 'legacy' component connection.

To configure this in jabberd2:

Add the secret in the router.xml configuration file.

Example :

  <!-- Shared secret used to identify legacy components (that is,
         "jabber:component:accept" components that authenticate using
         the "handshake" method). If this is commented out, support for
         legacy components will be disabled. -->
    <secret>palaver15cool</secret>

3. Configure Palaver

Twisted applications are generally run from taps, which store the
configuration information and other things.  To make a tap, one can
create a configuration file (see example-config.xml for a commented example)
and run:

  mktap palaver -c ./config.xml 

or specify all the configuration options on the mktap command line:

mktap palaver --jid=chat.localhost --rhost=localhost --rport=5437 
              --secret=secret --spool=/var/spool/directory/

By default palaver uses the spool directory backend. If you do not use
a different backend then the spool option is required. 

For a memory only backend use --backend=memory.

For more more options run:

  mktap palaver --help

And finally, to launch the Palaver component as a daemon, twistd is used:
 
  twistd -f palaver.tap

Other common options to twistd are -n (no daemon) and -o (for no 
state saving).

Convert from legacy spool to new spool.
=======================================
If you would like to convert your old mu-conference spool into
palaver's spool format then you can run a convert script provided
in palaver's util directory.

 python util/legacyspool.py /var/lib/jabberd/old-mu-conference /var/lib/jabberd/new-conference

This will convert and move the new spool format into a new directory.
You can leave the new directory out and it will put the new format in with the
old format.


Configure for postgresql and convert from legacy to pgsql.
==========================================================

First configure palaver the same way as above. But for the backend you do
the following :


  <backend>
    <type>pgsql</type>
    <dbuser>muc</dbuser>
    <dbname>muc</dbname>
    <!-- <dbpass>secret</dbpass> -->
    <!-- <dbhostname>localhost</dbhostname> -->
   
  </backend>


Create the database :

shell> createdb muc

Then create the tables :

shell> psql muc < /path/to/palaver/db/muc-psql.sql

Then if you want to convert your old muc configuration to the new one, run the
following script:

python util/legacypgsql.py /var/lib/jabber/conference.localhost/ ./config.xml

You can run 'python util/legacypgsql.py' to find out other options.

Bugs, Support, and Mailing Lists
================================

If you find a bug we would greatly appreciate hearing about it.  A bug
reporting interface and tracker is available on the web at:

  http://onlinegamegroup.com/projects/palaver

To report a new bug clikc on 'New Ticket'.  To search bugs, use the search
box at the upper right corner.

We'd appreciate it if you did a quick search for the bug in the tracker
before submitting a new issue.  This helps reduce duplicate reports.

General questions and support may be answered by searching the wiki at:

  http://onlinegamegroup.com/projects/palaver

or by posting or reading the palaver-dev mailing list:

  http://onlinegamegroup.com/cgi-bin/mailman/listinfo/palaver-dev

Commit messages and bug traffic are sent to the palaver-issues list:

  http://onlinegamegroup.com/cgi-bin/mailman/listinfo/palaver-issues

Code Repository and Contributions
=================================

The current and past versions of palaver can always be found in the Subversion
repository.  This repository may be browsed online at:

  http://onlinegamegroup.com/projects/palaver/browser

Contributions are welcome from anyone.  Please send them to the palaver-dev
mailing list, or file bugs with patches attached.

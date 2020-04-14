Contents
========

  * [To the Impatient](#to-the-impatient)
    - [Required packages](#required-packages)
    - [Basic installation](#basic-installation)
  * [Installing ViewVC](#installing-viewvc)
  * [Configuring ViewVC](#configuring-viewvc)-
  * [Serving CVS Repositories](#serving-cvs-repositories)
  * [Serving Subversion Repositories](#serving-cvs-repositories)
  * [Running ViewVC Under Apache](#running-viewvc-under-apache)
    - [CGI Mode](#cgi-mode)
    - [WSGI Mode](#wsgi-mode)
    - [FastCGI Mode](#fastcgi-mode)
    - [mod_python Mode](#mod_python-mode)
  * [ViewVC Standalone Server](#viewvc-standalone-server)
  * [Commits Database](#commits-database)
  * [Upgrading ViewVC](#upgrading-viewvc)
  * [Getting Help](#getting-help)


To The Impatient
================

Congratulations on getting this far. :-)  


Required packages
-----------------

ViewVC requires some additional software in order to operate,
depending on what you want to do with it.

Minimum requirements:

  * Python 3.3+
      (http://www.python.org/)

For CVS support:

  * RCS, Revision Control System
      (http://www.cs.purdue.edu/homes/trinkle/RCS/)
  * GNU diff
      (http://www.gnu.org/software/diffutils/diffutils.html)
  * CvsGraph 1.5.0+ (for optional CVS graphical tree generation)
      (formerly at http://www.akhphd.au.dk/~bertho/cvsgraph/)

For Subversion support:

  * Subversion 1.14.0+ (binaries and Python bindings)
      (http://subversion.apache.org/)

Strongly recommended:

  * Pygments 1.1+ syntax highlighting engine
      (https://pygments.org/)
  * chardet character encoding detection library
      (https://chardet.github.io/)

There are a number of additional packages that you might need in order
to enable additional features of ViewVC.  Please see the relevant
sections of this document for details.


Basic installation
------------------

To start installing right away (on UNIX), run `./viewvc-install` from
the top directory of the ViewVC software package (or source code
checkout), answering the prompts as appropriate.

    $ ./viewvc-install
    
When it finishes, edit the file `viewvc.conf` that gets created in the
installation directory.  At a minimum, you'll want to tell ViewVC
where to find your repositories.  (We'll assume hereafter for the
purpose of our examples that you've installed ViewVC into
`<VIEWVC_DIR>`.)

Once installed, you need to expose your ViewVC installation as a
web-accessible service.  ViewVC ships with a simple standalone server
program.  While we don't recommend using it for a production
deployment, it can be useful for quickly testing that ViewVC is
operational and properly configured.  You can run that server from the
command-line, pointing it to your configuration file:

    $ <VIEWVC_DIR>/bin/standalone.py

For production-quality hosting of ViewVC as a service, you'll want to
integrate ViewVC with a web server capable of running CGI or WSGI
programs (such as Apache HTTP Server).  We'll discuss the various
options for doing so in subsequent sections of this document.


Installing ViewVC
=================

Installation of ViewVC is handled by the `viewvc-install` script.
When you run this script, you will be prompted for a installation root
path.  The default is `/usr/local/viewvc-VERSION` (where VERSION is
the version of this ViewVC release).  Be advised that the installer
actually writes the installation path into some of the installed
files, so ViewVC cannot be trivially moved to a different path after
the install.

`viewvc-install` will create any intermediate directories required. It
will prompt before overwriting user-managed configuration files that
may have been modified (such as `viewvc.conf` or the view templates),
thus making it safe to install over the top of a previous
installation. It will always overwrite program files, however.

While installation into `/usr/local` typically requires superuser
priveleges ('root'), ViewVC does not have to be installed as root, nor
does it run as root.  It is just as valid to place ViewVC in a
specific user's home directory, too.

NOTE: if your system uses a restrictive umask, you might need to
adjust the permissions of the directory structure that
`viewvc-install` creates so that, for example, the modules in the
`lib/` subdirectory are actually readable by the main programs in the
`bin/` subdirectory.


Configuring ViewVC
==================

ViewVC configuration lives in the file `viewvc.conf`, generally
located in the root of your installation directory.  Edit this file
with the text editor of your choice in order to modify ViewVC's
behavior.

In particular, you'll want to examine the following configuration
options:

  * `cvs_roots` (for individual CVS repositories)
  * `svn_roots` (for individual Subversion repositories)
  * `root_parents` (for collections of CVS or Subversion repositories)
  * `rcs_dir` (for CVS)

There are some other options that are usually nice to change. See
`viewvc.conf` for more information.  ViewVC provides a working,
default look. However, if you want to customize the look of ViewVC,
edit the files in `<VIEWVC_DIR>/templates`.  You need knowledge about
HTML to edit the templates.

NOTE: For security reasons, don't install ViewVC in such a way that
its configuration file becomes itself web-accessible, as that file may
contain system path information as well as database authentication
credentials that should not be public knowledge!


Serving CVS Repositories
========================

In order to server CVS repositories, ViewVC needs to be able to run
the RCS utility binaries (`co`, `rlog`, etc.).  If these programs
aren't installed in typical system executable path locations, use the
`rcs_bin` configuration option in `viewvc.conf` to tell ViewVC where
to look for them.

You'll also need to tell ViewVC where to find your CVS repositories.
Use the `cvs_roots` configuration option to list individual CVS
repositories that you wish to expose through ViewVC, or see the
`root_parents` option for a quick way to tell ViewVC to consider all
the subdirecties of a given "parent" directory as CVS repositories.

NOTE: It is common to find on a given system a single monolithic CVS
repository, with dozens of individual top-level modules for each
distinct project.  If you point ViewVC to that repository directory
using `cvs_roots`, it will show a single repository to your users.
However, you can choose instead to use the `root_parents`
configuration option, pointing at the same repository directory, to
cause ViewVC to treat those top-level modules as if they were instead
each their own CVS repository.


Serving Subversion Repositories
===============================

Unlike the CVS integration, which simply wraps the RCS and CVS utility
programs, the Subversion integration requires additional Python
libraries.  To use ViewVC with Subversion, make sure you have both
Subversion itself and the Subversion Python bindings installed.  These
can be obtained through typical package distribution mechanisms, or
may be build from source.  (See the files `INSTALL` and
`subversion/bindings/swig/INSTALL` in the Subversion source tree for
more details on how to build and install Subversion and its Python
bindings.)

Generally speaking, you'll know that your installation of Subversion's
bindings has been successful if you can import the `svn.core` module
from within your Python interpreter.  Here's an example of doing so
which doubles as a quick way to check what version of the Subversion
Python binding you have:

    % python
    Python 3.6.9 (default, Nov  7 2019, 10:44:02) 
    [GCC 8.3.0] on linux
    Type "help", "copyright", "credits" or "license" for more information.
    >>> from svn.core import *
    >>> "%s.%s.%s" % (SVN_VER_MAJOR, SVN_VER_MINOR, SVN_VER_PATCH)
    '1.14.0'
    >>>

Note that by default, Subversion installs its bindings in a location
that is not in Python's default module search path (for example, on
Linux systems the default is usually `/usr/local/lib/svn-python`).
You need to remedy this, either by adding this path to Python's module
search path, or by relocating the bindings to some place in that
search path.

For example, you might want to create a `.pth` file in your Python
installation directory's site-packages area which tells Python where
to find additional modules (in this case, you Subversion Python
bindings).  You would do this as follows (and as root):

    $ echo "/path/to/svn/bindings" > /path/to/python/site-packages/svn.pth

(Though, obviously, with the correct paths specified.)

Configuration of the Subversion repositories happens in much the same
way as with CVS repositories, except with the `svn_roots`
configuration variable instead of the `cvs_roots` one.


Running ViewVC Under Apache
===========================

Requires:

  * Apache HTTP Server 2.2+ (https://httpd.apache.org/)

By far, the most common way to deploy ViewVC is as a script running
behind a gateway interface of a web server such as Apache HTTP Server.
In this section, we'll discuss the various ways in which you can do
so.  Before we continue, though, there are a few requirements common
to all of these approaches.

First, you'll need to be familiar with how to configure Apache HTTP
Server in general on your platform.  This web server product is highly
modularized.  Its configuration is often segmented across many files.
Additionally, each of the binary modules that breathe life into
Apache's vast feature set is typically installed as a separate
package, with its own configuration stub(s) making up some of that
segmented configuration.  But the _details_ of that segmentation
differ across various operating system flavors.

For example, a common modern installation of Apache on a CentOS system
will have its basic configuration in `/etc/httpd/conf/httpd.conf`.
But that file will "include" additional module-specific configuration
files from `/etc/httpd/conf.modules.d/`, plus higher-level
configuration from `/etc/httpd/conf.d/`.

On a Debian-based system, you'll often find the primary configuration
in `/etc/apache2/apache2.conf`, with a symlink-driven system for
managing the optional pieces in `/etc/apache2/conf-available` and
`/etc/apache2/conf-enabled`; `/etc/apache2/mods-available` and
`/etc/apache2/mods-enabled`; and `/etc/apache2/sites-available` and
`/etc/apache2/sites-enabled`.

As you can imagine, it's hard to write specific configuration
instructions with that much variation.  For the purposes of our
instructions here, we'll simply refer to `httpd.conf` as a generic
name for "the set of all files that make up your Apache HTTP Server
configuration".

One thing common to all of the various ViewVC deployment options under
Apache, though, is that you need to grant permission for site visitors
to access anything at all associated with your ViewVC installation
directory.  So, in your `httpd.conf`, add configuration such as this:

    <Directory <VIEWVC_DIR>>
        ### For Apache 2.4.x, uncomment this:
        # Require all granted
    
        ### For Apache 2.2.x, uncomment these instead:
        # Order allow,deny
        # Allow from all
    </Directory>

...where, again, `<VIEWVC_DIR>` is the directory into which you've
install ViewVC.

In the subsections below, we'll discuss the various options you have
for running ViewVC in specific ways under Apache.  After you've
configured Apache using the approach you desire, be sure to restart
the Apache service.

You should also consider protecting your ViewVC instance from
server-whacking webcrawlers.  As ViewVC is a web-based application
which each page containing various links to other pages and views, you
can expect your server's performance to suffer if a webcrawler finds
your ViewVC instance and begins traversing those links.  We highly
recommend that you add your ViewVC location to a site-wide robots.txt
file.  See [Robots.txt](http://en.wikipedia.org/wiki/Robots.txt) for
more information.


CGI Mode
--------

Requires:

  * mod_cgi (generally included with Apache itself)

To run ViewVC under Apache HTTP Server in CGI mode, you need to first
ensure that Apache can execute CGI scripts at all.  In your
`httpd.conf` (or one of its included files), load the CGI module if it
isn't already loaded.

    LoadModule cgi_module libexec/mod_cgi.so

There are a handful of different ways now to tell Apache where and how
to expose your ViewVC service.  The easiest is to use the
`ScriptAlias` directive:

    ScriptAlias /viewvc <VIEWVC_DIR>/bin/cgi/viewvc.cgi

This tells Apache that incoming requests aimed at the URL /viewvc (or
any children thereof) should be passed off to ViewVC's CGI wrapper
script for handling.

Some other ways to expose ViewVC as a CGI script include copying the
`bin/cgi/viewvc.cgi` script into a server-wide common `cgi-bin`
location, or exposing using the Apache `Options +ExecCGI` and
`AddHandler cgi-script .cgi` directives to cause it to allow the
ViewVC wrapper script to be treated as an executable program (instead
of a plain, downloadable file) when installed in a more generally
web-accessible server location.  Consult the wealth of knowledge
around these approaches available online for details.


WSGI mode
---------

Requires:

  * mod_wsgi, compiled for Python 3 (https://github.com/GrahamDumpleton/mod_wsgi)

To run ViewVC under Apache HTTP Server in WSGI mode, you need to first
ensure that Apache can execute WSGI programs.  It does this using
`mod_wsgi`, which is typically not included in the main Apache
installation package.  So first, ensure that `mod_wsgi` is installed
on your system.

Then, in your `httpd.conf` (or one of its included files), load the
WSGI module if it isn't already loaded.

    LoadModule wsgi_module libexec/mod_wsgi.so

Now, again in `httpd.conf`, expose ViewVC's WSGI wrapper program at
the URL of your choice:

    WSGIScriptAlias /viewvc <VIEWVC_DIR>/bin/wsgi/viewvc.wsgi

You'll probably also need the following directive because of the
not-quite-sanctioned way that ViewVC manipulates Python objects.

    WSGIApplicationGroup %{GLOBAL}


FastCGI mode
------------

Requires:

  * mod_fcgid (http://httpd.apache.org/mod_fcgid/)
  * Flup (https://www.saddi.com/software/flup/)

FastCGI mode uses ViewVC's WSGI support (from above), but supports
using FastCGI, and is a somewhat hybrid approach of several of the
above methods.  Using this mode is convenient if you are already using
FastCGI to serve up other types of services (such as PHP-based ones)
from your web server and don't wish to load additional modules.

In your `httpd.conf` (or one of its included files), load the FastCGI
daemon module if it isn't already loaded.

    LoadModule fcgid_module libexec/mod_fcgid.so

Now, again in `httpd.conf`, expose ViewVC's FastCGI wrapper program at
the URL of your choice:

    ScriptAlias /viewvc <VIEWVC_DIR>/bin/wsgi/viewvc.fcgi


mod_python mode
---------------

Requires:

  * mod_python module 3.5.0+, compiled for Python 3 (http://modpython.org/)

Running ViewVC under mod_python is similar to the other approaches
mentioned.  In your `httpd.conf` (or one of its included files), load
the mod_python module if it isn't already loaded.

    LoadModule python_module libexec/mod_python.so

Again in `httpd.conf`, expose ViewVC at the URL alias of your choice.

    Alias /viewvc <VIEWVC_DIR>/bin/mod_python/viewvc.py

Now, we need to tell Apache that mod_python should handle requests for
this location.  You can do this explicitly:

    <Location /viewvc>
        SetHandler mod_python
        PythonHandler handler
    <Location>

...or you can simply tell Apache to consult the `.htaccess` file that
lives inside ViewVC's `bin/mod_python` directory will for the required
additional configuration:

    <Directory <VIEWVC_DIR>>
        AllowOverride FileInfo Options
    </Directory>


Additional Apache Considerations
================================

There are a number of other things you can do to improve your
Apache-based ViewVC deployment.  We'll cover some of them here.


Direct static document access
------------------------------

ViewVC's HTML templates reference various stylesheets and icons
provided by ViewVC itself.  By default, ViewVC generates URLs to those
artifacts which point back into ViewVC (using a magic syntax); ViewVC
in turn handles such magic URL requests by streaming back the contents
of the requested icon or stylesheet file.  While this simplifies the
configuration and initial deployment of ViewVC, it's not the most
efficient approach to deliver what is essentially static content.

To improve performance, consider carving out a URL space in your
webserver's configuration solely for this static content and instruct
ViewVC to use that space when generating URLs for that content.  For
example, you might add an Alias such as the following to your
`httpd.conf`:

    Alias /viewvc-docroot /usr/local/viewvc/templates/default/docroot

And then, in `viewvc.conf`, set the `docroot` option to the same
location:

    docroot = /viewvc-docroot

WARNING: As always when using Alias directives, be careful that you
have them in the correct order.  For example, if you use an ordering
such as the following, Apache will hand requests for your static
documents off to ViewVC as if they were versioned resources:

    ScriptAlias  /viewvc         /usr/local/viewvc/bin/wsgi/viewvc.wsgi
    Alias        /viewvc/static  /usr/local/viewvc/templates/default/docroot

The correct order would be:

    Alias        /viewvc/static  /usr/local/viewvc/templates/default/docroot
    ScriptAlias  /viewvc         /usr/local/viewvc/bin/wsgi/viewvc.wsgi

(Of course, it's best to avoid such namespace nesting altogether if
you can.)


Access control
--------------

ViewVC support a number of path-based authorization approaches for
your repositories, some of which require knowledge of username of the
person who is accessing your ViewVC instance.  You can configuration
Apache to require a username and password for ViewVC site visitors
using it's password-file-based (or another) authentication feature:

    <Location /viewvc>
        AllowOverride None
        AuthUserFile /path/to/passwd/file
        AuthName "ViewVC Access"
        AuthType Basic
        require valid-user
    </Location>

With such configuration in place, your ViewVC users will be required
to successfully complete a password challenge before getting access to
your ViewVC-exposed version control repository information.  Also,
you're well-positioned to enable ViewVC's path-based authorization
features (see the `authorizer` configuration option in `viewvc.conf`),
by which you can customized which bits of information are exposed to
which of your ViewVC users.


ViewVC Standalone Server
========================

ViewVC can be run as a standalone script which uses a simplistic,
built-in Python HTTP server.  We don't recommend that you use this
mode for a production deployment, but it is a handy way to test our
your ViewVC configuration without all the additional overhead of
installing, configuring, and maintaining a full-fledge web server
package.

To run ViewVC's standalone server, simply execute the script from the
ViewVC installation directory.

    $ <VIEWVC_DIR>/bin/standalone.py
    server ready at http://localhost:49152/viewvc

By default, the script will expose ViewVC at the above URL.  But you
can modify the hostname and port to which it binds using the `--host`
and `--port` command-line options.  You can also change the virtual
path location from `/viewvc` to something else with the
`--script-alias` command-line option.

For a full listing of supported command-line options, run the
standalone server with `--help`.



SQL CHECKIN DATABASE
--------------------


For commits database support:

  * MySQL (or MariaDB) 3.22+ and MySQLdb (or mysqlclient-python) 0.9.0 or
        later to create a commit database
          (https://www.mysql.com/)
          (https://mariadb.org/)
          (http://sourceforge.net/projects/mysql-python)
          (https://github.com/PyMySQL/mysqlclient-python)

This feature is a clone of the Mozilla Project's Bonsai database.  It
catalogs every commit in the CVS or Subversion repository into a SQL
database.  In fact, the databases are 100% compatible.

Various queries can be performed on the database.  After installing ViewVC,
there are some additional steps required to get the database working.

1) You need MySQL and MySQLdb (a Python DBAPI 2.0 module) installed.

2) You need to create a MySQL user who has permission to create databases.
   Optionally, you can create a second user with read-only access to the
   database.

3) Run the <VIEWVC_INSTALLATION_DIRECTORY>/bin/make-database script.  It will
   prompt you for your MySQL user, password, and the name of database you
   want to create.  The database name defaults to "ViewVC".  This script
   creates the database and sets up the empty tables.  If you run this on a
   existing ViewVC database, you will lose all your data!

4) Edit your <VIEWVC_INSTALLATION_DIRECTORY>/viewvc.conf file.
   There is a [cvsdb] section.  You will need to set:

      enabled = 1        # Whether to enable query support in viewvc.cgi
      host =             # MySQL database server host
      port =             # MySQL database server port (default is 3306)
      database_name =    # name of database you created with make-database
      user =             # read/write database user
      passwd =           # password for read/write database user
      readonly_user =    # read-only database user
      readonly_passwd =  # password for the read-only user

   Note that it's pretty safe in this instance for your read-only user
   and your read-write user to be the same.

5) At this point, you need to tell your version control system(s) to
   publish their commit information to the database.  This is done
   using utilities that ViewVC provides.

   To publish CVS commits into the database:

      Two programs are provided for updating the checkin database from
      a CVS repository, cvsdbadmin and loginfo-handler.  They serve
      two different purposes.  The cvsdbadmin program walks through
      your CVS repository and adds every commit in every file.  This
      is commonly used for initializing the database from a repository
      which has been in use.  The loginfo-handler script is executed
      by the CVS server's CVSROOT/loginfo system upon each commit.  It
      makes real-time updates to the checkin database as commits are
      made to the repository.

      To build a database of all the commits in the CVS repository
      /home/cvs, invoke: "./cvsdbadmin rebuild /home/cvs".  If you
      want to update the checkin database, invoke: "./cvsdbadmin
      update /home/cvs".  The update mode checks to see if a commit is
      already in the database, and only adds it if it is absent.

      To get real-time updates, you'll want to checkout the CVSROOT
      module from your CVS repository and edit CVSROOT/loginfo.  For
      folks running CVS 1.12 or better, add this line:

         ALL <VIEWVC_INSTALLATION_DIRECTORY>/bin/loginfo-handler %p %{sVv}

      If you are running CVS 1.11 or earlier, you'll want a slightly
      different command line in CVSROOT/loginfo:

        ALL <VIEWVC_INSTALLATION_DIRECTORY>/bin/loginfo-handler %{sVv}

      If you have other scripts invoked by CVSROOT/loginfo, you will
      want to make sure to change any running under the "DEFAULT"
      keyword to "ALL" like the loginfo handler, and probably
      carefully read the execution rules for CVSROOT/loginfo from the
      CVS manual.

      If you are running the Unix port of CVS-NT, the handler script
      need to know about it.  CVS-NT delivers commit information to
      loginfo scripts differently than the way mainstream CVS does.
      Your command line should look like this:

        ALL <VIEWVC_INSTALLATION_DIRECTORY>/bin/loginfo-handler %{sVv} cvsnt

   To publish Subversion commits into the database:

      To build a database of all the commits in the Subversion
      repository /home/svn, invoke: "./svndbadmin rebuild /home/svn".
      If you want to update the checkin database, invoke:
      "./svndbadmin update /home/svn".

      To get real time updates, you will need to add a post-commit
      hook (for the repository example above, the script should go in
      /home/svn/hooks/post-commit).  The script should look something
      like this:

        #!/bin/sh
        REPOS="$1"
        REV="$2"
        <VIEWVC_INSTALLATION_DIRECTORY>/bin/svndbadmin update \
            "$REPOS" "$REV"

      If you allow revision property changes in your repository,
      create a post-revprop-change hook script which uses the same
      'svndbadmin update' command as the post-commit script, except
      with the addition of the --force option:

        #!/bin/sh
        REPOS="$1"
        REV="$2"
        <VIEWVC_INSTALLATION_DIRECTORY>/bin/svndbadmin update --force \
            "$REPOS" "$REV"

      This will make sure that the checkin database stays consistent
      when you change the svn:log, svn:author or svn:date revision
      properties.

You should be ready to go.  Click one of the "Query revision history"
links in ViewVC directory listings and give it a try.

Upgrading ViewVC
================

See the file `upgrading-howto.html` in the `docs/` subdirectory for
information on changes you might need to make as you upgrade from one
major version of ViewVC to another.



Getting Help
============

If nothing seems to work:

  * Verify that you can execute CGI scripts at all.  Apache needs to
    have an ScriptAlias /cgi-bin or cgi-script Handler defined, for
    example, which are often overlooked.  Try to execute a simple
    CGI-script that often comes with the distribution of the
    webserver.

  * Review any entries in the webserver's error log.

If ViewVC seems to work, but doesn't show the expected result (for
example, your repositories appear empty):

  * Check whether the user as whom ViewVC is running has the required
    read permission to your repositories.  ViewVC generally runs as
    the same user that the web server does, often user 'nobody' or
    'httpd'.

  * Make sure that ViewVC can located your RCS utilities? (edit rcs_dir)

See if your problem has been addressed by the [ViewVC
FAQ](http://viewvc.org/faq.html).

Finally, if all else fails, contact the ViewVC development community
at https://github.com/viewvc/viewvc/issues.

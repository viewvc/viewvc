Contents
========

  * [To the Impatient](#to-the-impatient)
    - [Required packages](#required-packages)
    - [Basic installation](#basic-installation)
  * [Installing ViewVC](#installing-viewvc)
  * [Configuring ViewVC](#configuring-viewvc)-
  * [Serving CVS Repositories](#serving-cvs-repositories)
  * [Serving Subversion Repositories](#serving-cvs-repositories)
  * [Running ViewVC](#running-viewvc)
    - [Standlone mode](#standalone-mode)
    - [Apache CGI mode](#apache-cgi-mode)
    - [Apache WSGI mode](#apache-cgi-mode)
    - [Apache mod_python mode](#apache-mod_python-mode)
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

Strongly recommended for common functionality:

  * Pygments 1.1+ syntax highlighting engine
      (http://pygments.org)
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

  * cvs_roots (for individual CVS repositories)
  * svn_roots (for individual Subversion repositories)
  * root_parents (for collections of CVS or Subversion repositories)
  * rcs_dir (for CVS)

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
using `cvs_roots, it will show a single repository to your users.
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


APACHE CONFIGURATION
--------------------

1) Locate your Apache configuration file(s).

   Typical locations are /etc/httpd/httpd.conf,
   /etc/httpd/conf/httpd.conf, and /etc/apache/httpd.conf. Depending
   on how Apache was installed, you may also look under /usr/local/etc
   or /etc/local. Use the vendor documentation or the find utility if
   in doubt.

2) Depending on how your Apache configuration is setup by default, you
   might need to explicitly allow high-level access to the ViewVC
   install location.

      <Directory <VIEWVC_INSTALLATION_DIRECTORY>>
        # For Apache 2.4.x, use this:
        Require all granted

        # For Apache 2.2.x, use these instead:
        # Order allow,deny
        # Allow from all
      </Directory>

   For example, if ViewVC is installed in /usr/local/viewvc-1.3 on
   your system:

      <Directory /usr/local/viewvc-1.3>
        # For Apache 2.4.x, use this:
        Require all granted

        # For Apache 2.2.x, use these instead:
        # Order allow,deny
        # Allow from all
      </Directory>

3) Configure Apache to expose ViewVC to users at the URL of your choice.

   ViewVC provides several different ways to do this.  Choose one of
   the following methods:

   -----------------------------------
   METHOD A:  CGI mode via ScriptAlias
   -----------------------------------
   The ScriptAlias directive is very useful for pointing
   directly to the viewvc.cgi script.  Simply insert a line containing

      ScriptAlias /viewvc <VIEWVC_INSTALLATION_DIRECTORY>/bin/cgi/viewvc.cgi

   into your httpd.conf file.  Choose the location in httpd.conf where
   also the other ScriptAlias lines reside.  Some examples:

      ScriptAlias /viewvc /usr/local/viewvc-1.3/bin/cgi/viewvc.cgi

   ----------------------------------------
   METHOD B:  CGI mode in cgi-bin directory
   ----------------------------------------
   Copy the CGI scripts from
   <VIEWVC_INSTALLATION_DIRECTORY>/bin/cgi/*.cgi
   to the /cgi-bin/ directory configured in your httpd.conf file.

   You can override configuration file location using:

       SetEnv VIEWVC_CONF_PATHNAME /etc/viewvc.conf

   ------------------------------------------
   METHOD C:  CGI mode in ExecCGI'd directory
   ------------------------------------------
   Copy the CGI scripts from
   <VIEWVC_INSTALLATION_DIRECTORY>/bin/cgi/*.cgi
   to the directory of your choosing in the Document Root adding the following
   Apache directives for the directory in httpd.conf or an .htaccess file:

      Options +ExecCGI
      AddHandler cgi-script .cgi

   NOTE: For this to work mod_cgi has to be loaded.  And for the .htaccess file
   to be effective, "AllowOverride All" or "AllowOverride Options FileInfo"
   needs to have been specified for the directory.

   ------------------------------------------
   METHOD D:  Using mod_python (if installed)
   ------------------------------------------

   NOTE: To use a mod_python-based installation, you'll need
   mod_python 3.5.0 or better.
   
   Copy the Python scripts and .htaccess file from
   <VIEWVC_INSTALLATION_DIRECTORY>/bin/mod_python/
   to a directory being served by Apache.

   In httpd.conf, make sure that "AllowOverride All" or at least
   "AllowOverride FileInfo Options" are enabled for the directory
   you copied the files to.

   You can override configuration file location using:

       SetEnv VIEWVC_CONF_PATHNAME /etc/viewvc.conf

   ----------------------------------------
   METHOD E:  Using mod_wsgi (if installed)
   ----------------------------------------
   Copy the Python scripts file from
   <VIEWVC_INSTALLATION_DIRECTORY>/bin/wsgi/
   to the directory of your choosing.  Modify httpd.conf with the
   following directives:

      WSGIScriptAlias /viewvc <VIEWVC_INSTALLATION_DIRECTORY>/bin/wsgi/viewvc.wsgi

   You'll probably also need the following directive because of the
   not-quite-sanctioned way that ViewVC manipulates Python objects.

      WSGIApplicationGroup %{GLOBAL}

   NOTE: WSGI support in ViewVC is at this time quite rudimentary,
   bordering on downright experimental.  Your mileage may vary.

   -----------------------------------------
   METHOD F:  Using mod_fcgid (if installed)
   -----------------------------------------

   This uses ViewVC's WSGI support (from above), but supports using FastCGI,
   and is a somewhat hybrid approach of several of the above methods.

   Especially if fcgi is already being used for other purposes, e.g. PHP,
   also using fcgi can prevent the need for including additional modules
   (e.g. mod_python or mod_wsgi) within Apache, which may help lessen Apache's
   memory usage and/or help improve performance.

   This depends on mod_fcgid:

      http://httpd.apache.org/mod_fcgid/

   as well as the fcgi server from Python's flup package:

      http://pypi.python.org/pypi/flup
      http://trac.saddi.com/flup

   The following are some example httpd.conf fragments you can use to
   support this configuration:

      ScriptAlias /viewvc /usr/local/viewvc/bin/wsgi/viewvc.fcgi

4) [Optional] Provide direct access to icons, stylesheets, etc.

   ViewVC's HTML templates reference various stylesheets and icons
   provided by ViewVC itself.  By default, ViewVC generates URLs to
   those artifacts which point back into ViewVC (using a magic
   syntax); ViewVC in turn handles such magic URL requests by
   streaming back the contents of the requested icon or stylesheet
   file.  While this simplifies the configuration and initial
   deployment of ViewVC, it's not the most efficient approach to
   deliver what is essentially static content.

   To improve performance, consider carving out a URL space in your
   webserver's configuration solely for this static content and
   instruct ViewVC to use that space when generating URLs for that
   content.  For example, you might add an Alias such as the following
   to your httpd.conf:

      Alias /viewvc-docroot /usr/local/viewvc/templates/default/docroot

   And then, in viewvc.conf, set the 'docroot' option to the same
   location:

      docroot = /viewvc-docroot

   WARNING: As always when using Alias directives, be careful that you
   have them in the correct order.  For example, if you use an
   ordering such as the following, Apache will hand requests for your
   static documents off to ViewVC as if they were versioned resources:

      ScriptAlias /viewvc        /usr/local/viewvc/bin/wsgi/viewvc.fcgi
      Alias       /viewvc/static /usr/local/viewvc/templates/default/docroot

   The correct order would be:

      Alias       /viewvc/static /usr/local/viewvc/templates/default/docroot
      ScriptAlias /viewvc        /usr/local/viewvc/bin/wsgi/viewvc.fcgi

   (That said, it's best to avoid such namespace nesting altogether if
   you can.)

5) [Optional] Add access control.

   In your httpd.conf you can control access to certain modules by
   adding directives like this:

      <Location "<url to viewvc.cgi>/<modname_you_wish_to_access_ctl>">
        AllowOverride None
        AuthUserFile /path/to/passwd/file
        AuthName "Client Access"
        AuthType Basic
        require valid-user
      </Location>

   WARNING: If you enable the "checkout_magic" or "allow_tar" options, you
   will need to add additional location directives to prevent people
   from sneaking in with URLs like:

      http://<server_name>/viewvc/*checkout*/<module_name>
      http://<server_name>/viewvc/~checkout~/<module_name>
      http://<server_name>/viewvc/<module_name>.tar.gz?view=tar

6) Restart Apache.

   The commands to do this vary.  "httpd -k restart" and "apache -k
   restart" are two common variants.  On RedHat Linux it is done using
   the command "/sbin/service httpd restart" and on SuSE Linux it is
   done with "rcapache restart".  Other systems use "apachectl restart".

7) [Optional] Protect your ViewVC instance from server-whacking webcrawlers.

   As ViewVC is a web-based application which each page containing various
   links to other pages and views, you can expect your server's performance
   to suffer if a webcrawler finds your ViewVC instance and begins
   traversing those links.  We highly recommend that you add your ViewVC
   location to a site-wide robots.txt file.  Visit the Wikipedia page
   for Robots.txt (http://en.wikipedia.org/wiki/Robots.txt) for more
   information.


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

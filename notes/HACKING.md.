# Testing and Reporting

Testing usability and the installation process on different platforms
is also a valuable contribution.  Please report your results back to
us developers.  Bandwidth is getting cheaper daily, so don't be afraid
-- in fact, feel encouraged -- to dump as much detail about the
problems you are seeing as possible into your bug reports.  Here are
some things you definitely should try to include:

  * What version of ViewVC you are using (if you are using a source
    snapshot, tell us the date of that snapshot).

  * What operating system your ViewVC is running on.

  * What version of Python you are using.

  * Whether you are running ViewVC standalone, or as a CGI program
    under a web server (and if so, what web server).

  * The URL of your ViewVC instantiation, if it is public.
    Sometimes, letting developers see the problem for themselves can
    save everyone alot of time.

# Coding Style

Unlike its predecessor, CvsWeb, ViewVC is written in Python, so it
doesn't suffer from the "unmaintainable code effect" that hits most
Perl projects sooner or later:

    "[Perl] combines all the worst aspects of C and Lisp: a
    billion different sublanguages in one monolithic executable.  It
    combines the power of C with the readability of
    PostScript."  -- Jamie Zawinski

Of course, a symphony of insanity can be composed in any language, so
we do try to stick to some basic guiding principles.  Maintain
whatever style is present in the code being modified.  New code can
use anything sane (which generally
means [PEP 8](http://www.python.org/dev/peps/pep-0008/)).
Our only real peeve is if someone writes a function call as:
`some_func (args)` -- that space between the function name and opening
parenthesis is Huge Badness.

Otherwise... _shrug_.

# Security

Since ViewVC is used on the Internet, security is a major concern.  If
you need to pass data from the request into an external program,
please don't use `os.system()` or `os.popen()`.  Please use the module
`lib/popen.py` that is included in the ViewVC distribution instead.

You might also wish to consult the list of previously reported
[security vulnerabilities](./SECURITY.md) to get an idea
of what kinds of bugs ViewVC has historically had in this area.  That
knowledge could just help you to avoid introducing similar problems
into future releases.

# Adding Features

If you need a new configuration option think carefully, into which
section it belongs.  Try to keep the content of `cgi/viewvc.conf.dist`
file and the library module `lib/config.py` in sync.

Because ViewVC is a Web-based application, people will have ViewVC
URLs hyperlinked from other sites, embedded in emails, bookmarked in
their browsers, etc.  It is very important to ensure that those URLs
continue to retrieve the information they were intended to retrieve
even if ViewVC is upgraded on the hosting server.  In other words, as
new features require modifications to the [ViewVC URL
schema](./docs/url-reference.html), make sure those modifications
preserve the existing functionality of all ViewVC URLs.

If a new file or module is added, a new line in the installer program
`viewvc-install` is required.

# Hacking on Templates

The library module `ezt.py` contains a module docstring which
describes the directives used in the HTML templates used by ViewVC.
The templates themselves can be found in the `templates` subdirectory.
We're currently developing a how-to guide for [ViewVC template
customization](./docs/template-authoring-guide.html).

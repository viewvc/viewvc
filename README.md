# ViewVC - Version Control Browser Interface

ViewVC is a browser interface for CVS and Subversion version control repositories. It generates templatized HTML to present navigable directory, revision, and change log listings. It can display specific versions of files as well as diffs between those versions. Basically, ViewVC provides the bulk of the report-like functionality you expect out of your version control tool, but much more prettily than the average textual command-line program output.

## Features

*   Support for filesystem-accessible CVS and Subversion repositories.
*   Support for path-based authorization, including parsing and honoring Subversion authz configuration files.
*   RSS feed generation for tracking changes to repositories or individual items within repositories.
*   Individually configurable virtual host support.
*   Line-based annotation/blame display.
*   Revision graph capabilities (via integration with [CvsGraph](http://www.akhphd.au.dk/~bertho/cvsgraph/)) (_CVS only_).
*   Syntax highlighting support.
*   [Bonsai](http://www.mozilla.org/projects/bonsai/)-like repository query facilities.
*   Template-driven output generation.
*   Colorized, side-by-side differences.
*   Tarball generation (by tag/branch for CVS, by revision for Subversion).
*   Localization support based on the Accept-Language request header.
*   Ability to run either as CGI script or as a standalone server.
*   Regexp-based file searching.
*   INI-like configuration file (as opposed to requiring actual code tweaks).

## Requirements

The only hard software requirement for running ViewVC is a suitable version of Python. The specifics of that, as well as all other requirements, depend on what you want to do with the tool. As those have changed somewhat over the years, it's best to consult the INSTALL file of the specific ViewVC release you wish to evaluate for its exact requirements. Here are pointers to the INSTALL files for the current major release lines:

*   [ViewVC 1.1.x](https://raw.githubusercontent.com/viewvc/viewvc/1.1.x/INSTALL)
*   [Unreleased bleeding edge (1.2-dev)](https://raw.githubusercontent.com/viewvc/viewvc/master/INSTALL)

## Getting ViewVC

Official ViewVC release archives are available for download at http://viewvc.org/downloads/.  To see what changes have been included in the release, see the [CHANGES](https://raw.githubusercontent.com/viewvc/viewvc/master/CHANGES) file.

Un-official nightly builds are available at http://viewvc.org/nightly/

## Upgrading

We've tried to ensure that ViewVC URLs are stable, and that even when we deprecate a particular URL syntax, we continue to support the handling of it (using HTTP redirects to point browsers to the new form of that URL). We know that ViewVC URLs get bookmarked, and nobody likes when their bookmarked URLs suddenly stop working.

Across patch releases of ViewVC (when only the Z component of version X.Y.Z changes), we do our best to keep the configuration file syntax and template data dictionary unchanged, too. This makes it much easier for folks who need to upgrade quickly to get security or other bug fixes. But across major and minor releases, all bets are off, and chances are good that we've done some major plumbing. When upgrading your ViewVC instance across major or minor version numbers, you'll almost certainly want to consult the "Upgrading HOWTO" document in the `docs/` directory of the release archive for tips on how to migrate your configuration files and any template customizations you've made into their new formats.

## Contributing

Some notes for contributing to ViewVC's source code are include in our [HACKING.md](./notes/HACKING.md) document.

## Questions or Concerns?

Feel free to use our [Issue Tracker](https://github.com/viewvc/viewvc/issues) to ask questions, make feature requests, report bugs, etc.  In yesteryear, we had mailing lists for this kind of thing, but those have been discontinued.

## ViewVC Docker Images

GitHub user @cmanley has graciously assembled Docker images for running ViewVC.  See his work at https://github.com/cmanley/viewvc-docker.

## License

**Copyright © 1999-2017 The ViewCVS Group. All rights reserved.**

By using ViewVC, you agree to the terms and conditions set forth below:

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

1.  Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
2.  Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE AUTHOR AND CONTRIBUTORS ``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE AUTHOR OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

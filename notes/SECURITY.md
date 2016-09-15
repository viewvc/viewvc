## Security Issue History

### [CVE-2002-0771](http://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2002-0771)

  * **Vulnerable Version(s)**: 0.8 - 0.9.2
  * **Fixed Version(s)**: 0.9.3
  * **Issue(s)**:
  * **Description**: Cross-site scripting vulnerability in `viewcvs.cgi` for ViewCVS 0.9.2 allows remote attackers to inject script and steal cookies via the (1) cvsroot or (2) sortby parameters.

### [CVE-2004-0915](http://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2004-0915)

  * **Vulnerable Version(s)**: 0.9.2
  * **Fixed Version(s)**: 0.9.3
  * **Issue(s)**:
  * **Description**: Multiple unknown vulnerabilities in viewcvs before 0.9.2, when exporting a repository as a tar archive, does not properly implement the `hide_cvsroot` and `forbidden` settings, which could allow remote attackers to gain sensitive information.

### [CVE-2004-1062](http://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2004-1062)

  * **Vulnerable Version(s)**: 0.9.2
  * **Fixed Version(s)**: 0.9.3
  * **Issue(s)**:
  * **Description**: Multiple cross-site scripting (XSS) vulnerabilities in ViewCVS 0.9.2 allow remote attackers to inject arbitrary HTML and web script via certain error messages.

### [CVE-2005-4830](http://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2005-4830)

  * **Vulnerable Version(s)**: 0.9.2
  * **Fixed Version(s)**: 0.9.3
  * **Issue(s)**:
  * **Description**: CRLF injection vulnerability in viewcvs in ViewCVS 0.9.2 allows remote attackers to inject arbitrary HTTP headers and conduct HTTP response splitting attacks via CRLF sequences in the `content-type` parameter.

### [CVE-2005-4831](http://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2005-4831)

  * **Vulnerable Version(s)**: 0.9.2 - 0.9.4, 1.0.0 - 1.0.5
  * **Fixed Version(s)**: 1.0.6
  * **Issue(s)**: <a href="http://viewvc.tigris.org/issues/show_bug.cgi?id=354">354</a>
  * **Description**: viewcvs in ViewCVS 0.9.2 allows remote attackers to set the Content-Type header to arbitrary values via the `content-type` parameter, which can be leveraged for cross-site scripting (XSS) and other attacks, as demonstrated using (1) "text/html", or (2) "image/jpeg" with an image that is rendered as HTML by Internet Explorer, a different vulnerability than CVE-2004-1062. NOTE: it was later reported that 0.9.4 is also affected.

### [CVE-2006-5442](http://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2006-5442)

  * **Vulnerable Version(s)**: 0.9.2 - 0.9.4, 1.0.0 - 1.0.2
  * **Fixed Version(s)**: 1.0.3
  * **Issue(s)**:
  * **Description**: ViewVC 1.0.2 and earlier does not specify a charset in its HTTP headers or HTML documents, which allows remote attackers to conduct cross-site scripting (XSS) attacks that inject arbitrary UTF-7 encoded JavaScript code via a view.

### [CVE-2008-1290](http://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2008-1290)

  * **Vulnerable Version(s)**: 0.9.2 - 0.9.4, 1.0.0 - 1.0.4
  * **Fixed Version(s)**: 1.0.5
  * **Issue(s)**:
  * **Description**: ViewVC before 1.0.5 includes "all-forbidden" files within search results that list CVS or Subversion (SVN) commits, which allows remote attackers to obtain sensitive information.

### [CVE-2008-1291](http://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2008-1291)

  * **Vulnerable Version(s)**: 0.9.2 - 0.9.4, 1.0.0 - 1.0.4
  * **Fixed Version(s)**: 1.0.5
  * **Issue(s)**:
  * **Description**: ViewVC before 1.0.5 stores sensitive information under the web root with insufficient access control, which allows remote attackers to read files and list folders under the hidden `CVSROOT` folder.

### [CVE-2008-1292](http://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2008-1292)

  * **Vulnerable Version(s)**: 0.9.2 - 0.9.4, 1.0.0 - 1.0.4
  * **Fixed Version(s)**: 1.0.5
  * **Issue(s)**:
  * **Description**: ViewVC before 1.0.5 provides revision metadata without properly checking whether access was intended, which allows remote attackers to obtain sensitive information by reading (1) forbidden pathnames in the revision view, (2) log history that can only be reached by traversing a forbidden object, or (3) forbidden diff view path parameters.

### [CVE-2008-4325](http://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2008-4325)

  * **Vulnerable Version(s)**: 0.9.2 - 0.9.4, 1.0.0 - 1.0.5
  * **Fixed Version(s)**: 1.0.6
  * **Issue(s)**: <a href="http://viewvc.tigris.org/issues/show_bug.cgi?id=354">354</a>
  * **Description**: `lib/viewvc.py` in ViewVC 1.0.5 uses the `content-type` parameter in the HTTP request for the Content-Type header in the HTTP response, which allows remote attackers to cause content to be misinterpreted by the browser via a `content-type` parameter that is inconsistent with the requested object. NOTE: this issue might not be a vulnerability, since it requires attacker access to the repository that is being viewed.

### [CVE-2009-3618](http://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2009-3618)

  * **Vulnerable Version(s)**: 1.0.0 - 1.0.8, 1.1.0 - 1.1.1
  * **Fixed Version(s)**: 1.0.9, 1.1.2
  * **Issue(s)**:
  * **Description**: Cross-site scripting (XSS) vulnerability in viewvc.py in ViewVC 1.0 before 1.0.9 and 1.1 before 1.1.2 allows remote attackers to inject arbitrary web script or HTML via the view parameter. NOTE: Some of these details are obtained from third party information.

### [CVE-2009-3619](http://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2009-3619)

  * **Vulnerable Version(s)**: 1.0.0 - 1.0.8, 1.1.0 - 1.1.1
  * **Fixed Version(s)**: 1.0.9, 1.1.2
  * **Issue(s)**:
  * **Description**: Unspecified vulnerability in ViewVC 1.0 before 1.0.9 and 1.1 before 1.1.2 has unknown impact and remote attack vectors related to "printing illegal parameter names and values".

### [CVE-2009-5024](http://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2009-5024)

  * **Vulnerable Version(s)**: 0.9.2 - 0.9.4, 1.0.0 - 1.0.12, 1.1.0 - 1.1.10
  * **Fixed Version(s)**: 1.0.13, 1.1.11
  * **Issue(s)**:
  * **Description**: ViewVC before 1.1.11 allows remote attackers to bypass the cvsdb `row_limit` configuration setting, and consequently conduct resource-consumption attacks, via the limit parameter, as demonstrated by a "query revision history" request.

### [CVE-2010-0004](http://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2010-0004)

  * **Vulnerable Version(s)**: 1.1.0 - 1.1.2
  * **Fixed Version(s)**: 1.1.3
  * **Issue(s)**:
  * **Description**: ViewVC before 1.1.3 composes the root listing view without using the authorizer for each root, which might allow remote attackers to discover private root names by reading this view.

### [CVE-2010-0005](http://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2010-0005)

  * **Vulnerable Version(s)**: 1.1.0 - 1.1.2
  * **Fixed Version(s)**: 1.1.3
  * **Issue(s)**:
  * **Description**: `query.py` in the query interface in ViewVC before 1.1.3 does not reject configurations that specify an unsupported authorizer for a root, which might allow remote attackers to bypass intended access restrictions via a query.

### [CVE-2010-0132](http://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2010-0132)

  * **Vulnerable Version(s)**: 1.0.0 - 1.0.10, 1.1.0 - 1.1.4
  * **Fixed Version(s)**: 1.0.11, 1.1.5
  * **Issue(s)**:
  * **Description**: Cross-site scripting (XSS) vulnerability in ViewVC 1.1 before 1.1.5 and 1.0 before 1.0.11, when the regular expression search functionality is enabled, allows remote attackers to inject arbitrary web script or HTML via vectors related to "search_re input," a different vulnerability than CVE-2010-0736.

### [CVE-2010-0736](http://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2010-0736)

  * **Vulnerable Version(s)**: 1.0.0 - 1.0.9, 1.1.0 - 1.1.3
  * **Fixed Version(s)**: 1.0.10, 1.1.4
  * **Issue(s)**:
  * **Description**: Cross-site scripting (XSS) vulnerability in the `view_queryform` function in `lib/viewvc.py` in ViewVC before 1.0.10, and 1.1.x before 1.1.4, allows remote attackers to inject arbitrary web script or HTML via "user-provided input.

### [CVE-2012-3356](http://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2012-3356)

  * **Vulnerable Version(s)**: 1.1.0 - 1.1.14
  * **Fixed Version(s)**: 1.1.15
  * **Issue(s)**:
  * **Description**: The remote SVN views functionality (`lib/vclib/svn/svn_ra.py`) in ViewVC before 1.1.15 does not properly perform authorization, which allows remote attackers to bypass intended access restrictions via unspecified vectors.

### [CVE-2012-3357](http://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2012-3357)

  * **Vulnerable Version(s)**: 1.1.0 - 1.1.14
  * **Fixed Version(s)**: 1.1.15
  * **Issue(s)**:
  * **Description**: The SVN revision view (`lib/vclib/svn/svn_repos.py`) in ViewVC before 1.1.15 does not properly handle log messages when a readable path is copied from an unreadable path, which allows remote attackers to obtain sensitive information, related to a "log msg leak.

### [CVE-2012-4533](http://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2012-4533)

  * **Vulnerable Version(s)**: 1.0.0 - 1.0.12, 1.1.0 - 1.1.15
  * **Fixed Version(s)**: 1.0.13, 1.1.16
  * **Issue(s)**: <a href="http://viewvc.tigris.org/issues/show_bug.cgi?id=515">515</a>
  * **Description**: Cross-site scripting (XSS) vulnerability in the "extra" details in the `DiffSource._get_row` function in `lib/viewvc.py` in ViewVC 1.0.x before 1.0.13 and 1.1.x before 1.1.16 allows remote authenticated users with repository commit access to inject arbitrary web script or HTML via the "function name" line.

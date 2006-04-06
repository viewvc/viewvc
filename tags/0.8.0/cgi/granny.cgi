#!/usr/bin/python
# -*- Mode: python -*-

"""
Granny.py - display CVS annotations in HTML
with lines colored by code age in days.

Original Perl version by J. Gabriel Foster (gabe@sgrail.com)
   Posted to info-cvs on 02/27/1997
   You can still get the original shell archive here:
     http://www.geocrawler.com/archives/3/382/1997/2/0/2103824/

Perl modifications for NT by Marc Paquette (marcpa@cam.org)

Python port and CGI modifications by Brian Lenihan (brianl@real.com)

 From the original granny.pl README:

--
What is Granny?  Why do I care?

   Granny is a tool for viewing cvs annotation information graphically.  Using
   Netscape, granny indicates the age of lines by color.  Red lines are new,
   blue lines are old.  This information can be very useful in determining
   what lines are 'hot'.  New lines are more likely to contain bugs, and this
   is an easy way to visualize that information.

     Requirements:
         Netscape (version 2.0 or better)
         Perl5
         CVS 1.9 (1.8 should work, but I have not tried it.)

     Installation:
         Put granny somewhere in your path.  You may need to edit the
         first line to point to your perl5 binary and libraries.

     What to do:
         Run granny just like you would 'cvs annotate' for a single file.
             granny thefile.C

         To find out who is to blame for that new 'feature'.
             granny -U thefile.C

         For all your options:
             granny -h

   Questions, Comments, Assertions?
     send e-mail to the author: Gabe Foster (gabe@sgrail.com)

   Notes:
   I'm not the first person to try this sort of display, I just read about it
   in a magazine somewhere and decided that cvs had all the information
   I needed.  To whomever first had this idea, it's a great one.

   Granny is free, please use it as you see fit.  I give no warranties.
   As a courtesy, I ask that you tell me about any modifications you have made,
   and also ask that you acknowledge my work if you use Granny in your own
   software.
--


Granny.py:

granny.py [-h][-d days][-i input][-o output][-DUV] file


-h:      Get this help display.
-i:      Specify the input file. (Use - for stdin.)
-o:      Specify the output file. (Use - for stdout.)
-d:      Specify the day range for the coloring.\n
-r:      Specify the cvs revision of the file.
-D:      Display the date the line was last edited.
-U       Display the user that last edited the line.
-V:      Display the version the line was last edited.

By default, granny.py executes cvs annotate on a FILE and
runs netscape to display the graphic.

It is assumed that cvs and Netscape (for command line version) are
in your path.

If granny.py is placed in the cgi-bin directory of your Web
server, it will act as a CGI script. The working directory
defaults to /usr/tmp, but it can be overridden in the class
constructor:

     A = CGIAnnotate(tempdir='/tmp')

Required fields:

root        The full path to the cvs root directory.
Name        The module/filename of the annotated file.

Optional fields:

rev         The cvs revision number to use. (default HEAD).

Set the following fields to display extra info:

showUser    Display the user that last edited the line.
showVersion Display version that the line was last edited in.
showDate    Display the date the line was last edited.

http://yourserver.yourdomain.com/cgi-bin/granny.py?root=/cvsroot&Name=module/file


TODO:

Add support for determining the MIME type of files and/or a binary check.
   - easily done by parsing Apache (mime.conf) or Roxen (extensions) MIME 
files.
Consider adding buttons to HTML for optional display fields.
Add support for launching other browsers.

"""

import os
import sys
import string
import re
import time
import getopt
import cStringIO
import tempfile
import traceback


month_num = {
     'Jan' : 1, 'Feb' : 2, 'Mar' : 3, 'Apr' : 4, 'May' : 5, 'Jun' : 6,
      'Jul' : 7, 'Aug' : 8, 'Sep' : 9, 'Oct' : 10, 'Nov' : 11, 'Dec' : 12
}

class Annotate:
     def __init__(self):
         self.day_range = 365
         self.counter = 0
         self.color_table = {}
         self.user = {}
         self.version = {}
         self.rtime = {}
         self.source = {}
         self.tmp = None
         self.tmpfile = None
         self.revision = ''
         self.showUser = 0
         self.showDate = 0
         self.showVersion = 0
         self.set_today()


     def run(self):
         try:
             self.process_args()
             self.parse_raw_annotated_file()
             self.write_annotated_html_file()
             if self.tmp:
                 self.display_annotated_html_file()
         finally:
             if sys.exc_info()[0] is not None:
                 traceback.print_exc()
             self.cleanup()


     def cleanup(self):
         if self.tmp:
             self.tmp.close()
             os.unlink(self.tmpfile)
         sys.exit(0)


     def getoutput(self, cmd):
         """
         Get stdin and stderr from cmd and
         return exit status and captured output
         """

         if os.name == 'nt':
             # os.popen is broken on win32, but seems to work so far...
             pipe = os.popen('%s 2>&1' % cmd, 'r')
         else:
             pipe = os.popen('{ %s ; } 2>&1' % cmd, 'r')
         text = pipe.read()
         sts = pipe.close()
         if sts == None:
             sts = 0
         if text[:-1] == '\n':
             text = text[-1:]
         return sts, text


     def set_today(self):
         """
         compute the start of this day
         """
         (year,mon,day,hour,min,sec,dow,doy,dst) = time.gmtime(time.time())
         self.today = time.mktime((year,mon,day,0,0,0,0,0,0))


     def get_today(self):
         return self.today


     # entify stuff which breaks HTML display
     # this was lifted from some Zope Code in
     # StructuredText.py
     #
     # XXX try it with string.replace and run it in the profiler

     def html_quote(self,v,
          character_entities=((re.compile('&'), '&amp;'),
                              (re.compile("<"), '&lt;' ),
                              (re.compile(">"), '&gt;' ),
                              (re.compile('"'), '&quot;'))):
         gsub = re.sub

         text=str(v)
         for regexp,name in character_entities:
             text=gsub(regexp,name,text)
         return text


     def display_annotated_html_file(self):
         if os.name == 'nt':
             path = '"C:\\Program Files\\Netscape\\Communicator'\
                    '\\Program\\Netscape"'

             if os.system('%s %s' % (path, self.tmpfile)) != 0:
                 sys.stderr.write('%s: Unable to start Netscape' % sys.argv[0])
                 sys.exit(1)
         else:
             if os.system('netscape -remote openFile\(%s\)' %
                                                          self.tmpfile) != 0:
                 sys.stderr.write('%s: Trying to run netscape, please wait\n' %
                                                          sys.argv[0])
                 if os.system('netscape &') == 0:
                     for i in range(10):
                         time.sleep(1)
                         if os.system('netscape -remote openFile\(%s\)' %
                                                          self.tmpfile) == 0:
                             break
                     if i == 10:
                         sys.stderr.write('%s:Unable to start netscape\n' %
                                                          sys.argv[0])
                 else:
                     sys.stderr.write('%s:Unable to start netscape\n' %
                                                          sys.argv[0])

         # give Netscape time to read the file
         # XXX big files may raise an OSError exception on NT
         # if the sleep is too short.
         time.sleep(5)


     def get_opts(self):
         opt_dict = {}
         if not len(sys.argv[1:]) > 0:
             self.usage()

         opts, args = getopt.getopt(sys.argv[1:], 'DUVhi:o:d:r:')
         for k,v in opts:
             opt_dict[k] = v
         return opt_dict


     def process_args(self):
         opts = self.get_opts()

         if opts.has_key('-r'):
             self.revision = '-r%s' % opts['-r']

         if opts.has_key('-h'):
             self.usage(help=1)

         if opts.has_key('-i'):
             if opts['-i'] != '-':
                 self.filename = v
                 infile = open(filename, 'r')
                 sys.stdin = infile
             else:
                 self.file = sys.stdin
         else:
             self.filename = sys.argv[len(sys.argv) - 1]

             cmd = 'cvs annotate %s %s' % (self.revision, self.filename)

             status, text = self.getoutput(cmd)

             if status != 0 or text == '':
                 sys.stderr.write("Can't run cvs annotate on %s\n" %
                                                                 self.filename)
                 sys.stderr.write('%s\n' % text)
                 sys.exit(1)
             self.file = cStringIO.StringIO(text)


         if opts.has_key('-o'):
             if opts['-o'] != '-':
                 outfile = open(v, 'w')
                 sys.stdout = outfile
         else:
             # this could be done without a temp file
             target = sys.argv[len(sys.argv) -1]
             self.tmpfile = tempfile.mktemp()
             self.tmp = open(self.tmpfile, 'w')
             sys.stdout = self.tmp


         if opts.has_key('-d'):
             if opts['-d'] > 0:
                 self.day_range = opts['-d']

         if opts.has_key('-D'):
             self.showDate = 1

         if opts.has_key('-U'):
             self.showUser = 1

         if opts.has_key('-V'):
             self.showVersion = 1


     def parse_raw_annotated_file(self):
         ann = re.compile('((\d+\.?)+)\s+\((\w+)\s+(\d\d)-'\
                          '(\w{3})-(\d\d)\): (.*)')

         text = self.file.read()
         lines = string.split(text, '\n')
         for line in lines:
             # Parse an annotate string
             m = ann.search(line)
             if m:
                 self.version[self.counter] = m.group(1)
                 self.user[self.counter] = m.group(3)
                 oldtime = self.today - time.mktime((
                                                 int(m.group(6)),
                                                 int(month_num[m.group(5)]),
                                                 int(m.group(4)),0,0,0,0,0,0))

                 self.rtime[self.counter] = oldtime / 86400
                 self.source[self.counter] = self.html_quote(m.group(7))
             else:
                 self.source[self.counter] = self.html_quote(line)
                 pass
             self.counter = self.counter + 1


     def write_annotated_html_file(self):
         if os.environ.has_key('SCRIPT_NAME'):
             print 'Status: 200 OK\r\n'
             print 'Content-type: text/html\r\n\r\n'

         print ('<html><head><title>%s</title></head>\n' \
                '<body bgcolor="#000000">\n' \
                '<font color="#FFFFFF"><H1>File %s</H1>\n' \
                '<H3>Code age in days</H2>' % (self.filename, self.filename))

         for i in range(self.day_range + 1):
             self.color_table[i] = \
                 self.hsvtorgb(240.0 * i / self.day_range, 1.0, 1.0)

         step = self.day_range / 40
         if step < 5:
             step = 1
             while self.day_range/step > 40:
                 step = step + 1
         if step >= 5:
             if step != 5:
                 step = step + 5 - (step % 5)
             while self.day_range / step > 20:
                 step = step + 5

         for i in range(self.day_range + 1, step):
             print '<font color=%s>%s ' % (self.color_table[i], i),
         print '<pre><code>'

         for i in range(self.counter):
             if self.showUser and self.user.has_key(i):
                 print '%s%s ' % ('<font color=#FFFFFF>',
                                  string.ljust(self.user[i],10)),

             if self.showVersion and self.version.has_key(i):
                 print '%s%s ' % ('<font color=#FFFFFF>',
                                  string.ljust(self.version[i],6)),

             if self.showDate and self.rtime.has_key(i):
                 (year,mon,day,hour,min,sec,dow,doy,dst) = time.gmtime(
                                            self.today - self.rtime[i] * 86400)

                 print '<font color=#FFFFFF>%02d/%02d/%4d ' % (mon, day, year),


             if self.rtime.get(i, self.day_range) < self.day_range:
                 fcolor = self.color_table.get(
                                         self.rtime[i],
                                         self.color_table[self.day_range])
             else:
                 fcolor = self.color_table[self.day_range]

             print '<font color=%s> %s' % (fcolor, self.source[i])

         print ('</code></pre>\n' \
                '<font color=#FFFFFF>\n' \
                '<H5>Granny original Perl version by' \
                '<I>J. Gabriel Foster</I>\n' \
                '<ADDRESS><A HREF=\"mailto:gabe@sgrail.com\">'\
                'gabe@sgrail.com</A></ADDRESS>\n' \
                'Python version by <I>Brian Lenihan</I>\n' \
                '<ADDRESS><A HREF=\"mailto:brianl@real.com\">' \
                'brianl@real.com</A></ADDRESS>\n' \
                '</body></html>')

         sys.stdout.flush()


     def hsvtorgb(self,h,s,v):
         """
         a veritable technicolor spew
         """
         if s == 0.0:
             r = v; g = v; b = v
         else:
             if h < 0:
                 h = h + 360.0
             elif h >= 360.0:
                 h = h - 360.0
             h = h / 60.0
             i = int(h)
             f = h - i

             if s > 1.0:
                 s = 1.0
             p = v * (1.0 - s)
             q = v * (1.0 - (s * f))
             t = v * (1.0 - (s * (1.0 - f)))

             if   i == 0: r = v; g = t; b = p
             elif i == 1: r = q; g = v; b = p
             elif i == 2: r = p; g = v; b = t
             elif i == 3: r = p; g = q; b = v
             elif i == 4: r = t; g = p; b = v
             elif i == 5: r = v; g = p; b = q

         return '#%02X%02X%02X' % (r * 255 + 0.5, g * 255 + 0.5, b * 255 + 0.5)



     def usage(self, help=None):
         sys.stderr.write('\nusage: %s %s\n\n' % (
                         sys.argv[0],
                         '[-hDUV][-d days][-i input][-o output][-r rev] FILE')
         )

         if help is not None:
             sys.stderr.write(
                 '-h:      Get this help display.\n' \
                 '-i:      Specify the input file. (Use - for stdin.)\n' \
                 '-o:      Specify the output file. (Use - for stdout.)\n' \
                 '-d:      Specify the day range for the coloring.\n' \
                 '-r:      Specify the cvs revision of the file.\n' \
                 '-D:      Display the date the line was last edited.\n' \
                 '-U       Display the user that last edited the line.\n' \
                 '-V:      Display the version the line was last edited.\n\n' \
                 'By default, %s executes a cvs annotate on a FILE and\n' \
                 'runs netscape to display the graphical ' \
                 'annotation\n' % sys.argv[0]
             )

         sys.exit(0)



class CGIAnnotate(Annotate):
     def __init__(self,tempdir='/usr/tmp'):
         Annotate.__init__(self)
         if os.name == 'nt':
             self.tempdir = os.environ.get('TEMP') or os.environ.get('TMP')
         else:
             # XXX need a sanity check here
             self.tempdir = tempdir
         os.chdir(self.tempdir)

     def process_args(self):
         f = cgi.FieldStorage()
         cvsroot = f['root'].value
         if f.has_key('showUser'):
             self.showUser = 1
         if f.has_key('showDate'):
             self.showDate = 1
         if f.has_key('showVersion'):
             self.showVersion = 1
         if f.has_key('rev'):
             self.revision = '-r%s' % f['rev'].value
         path = f['Name'].value
         module = os.path.dirname(path)
         self.workingdir = 'ann.%s' % os.getpid()
         self.filename = os.path.basename(path)

         os.mkdir(self.workingdir)
         os.chdir(os.path.join(self.tempdir, self.workingdir))
         os.system('cvs -d %s co %s' % (cvsroot, path))
         os.chdir(module)

         cmd = 'cvs annotate %s %s' % (self.revision, self.filename)
         status, text = self.getoutput(cmd)

         if status != 0 or text == '':
             text = "Can't run cvs annotate on %s\n" % path
         self.file = cStringIO.StringIO(text)


     def cleanup(self):
         os.chdir(self.tempdir)
         os.system('rm -rf %s' % self.workingdir)


     def display_annotated_html_file(self):
         pass

     def usage(self):
         pass

if __name__ == '__main__':
     if os.environ.has_key('SCRIPT_NAME'):
         import cgi
         A = CGIAnnotate()
     else:
         A = Annotate()
     A.run()


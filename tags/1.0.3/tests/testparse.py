
MODULE = '/home/gstein/testing/cvsroot/mod_dav'
OUTPUT = 'rlog-dump'

import sys
sys.path.insert(0, '../lib')

import os
import rlog


def get_files(root):
  all_files = [ ]
  os.path.walk(root, _collect_files, all_files)
  all_files.sort()
  return all_files

def _collect_files(all_files, dir, files):
  for f in files:
    if f[-2:] == ',v':
      all_files.append(os.path.join(dir, f))

def get_config():
  class _blank:
    pass
  cfg = _blank()
  cfg.general = _blank()
  cfg.general.rcs_path = ''
  return cfg


def gen_dump(cfg, out_fname, files, func):
  out = open(out_fname, 'w')
  for f in files:
    data = func(cfg, f)
    out.write(data.filename + '\n')
    tags = data.symbolic_name_hash.keys()
    tags.sort()
    for t in tags:
      out.write('%s:%s\n' % (t, data.symbolic_name_hash[t]))
    for e in data.rlog_entry_list:
      names = dir(e)
      names.sort()
      for n in names:
        out.write('%s=%s\n' % (n, getattr(e, n)))

def _test():
  cfg = get_config()
  files = get_files(MODULE)
  gen_dump(cfg, OUTPUT + '.old', files, rlog.GetRLogData)
  gen_dump(cfg, OUTPUT + '.new', files, rlog.get_data)

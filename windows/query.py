import sapi
import query

s = sapi.ModPythonServer(Request)
try:
  query.main(s, 'viewcvs.py')
finally:
  s.close()
import sapi
import query

s = sapi.ModPythonServer(Request)
try:
  query.main('viewcvs.py')
finally:
  s.close()
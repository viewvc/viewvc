import sapi
import query
import apache

s = sapi.ModPythonServer(apache.GetRequest())
try:
  query.main('viewcvs.py')
finally:
  s.close()
import sapi
import viewcvs
import apache

s = sapi.ModPythonServer(apache.GetRequest())
try:
  viewcvs.main()  
finally:
  s.close()
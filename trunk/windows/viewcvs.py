import sapi
import viewcvs

s = sapi.ModPythonServer(Request)
try:
  viewcvs.main()  
finally:
  s.close()
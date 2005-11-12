import sapi
import viewcvs

s = sapi.ModPythonServer(Request)
try:
  viewcvs.main(s)  
finally:
  s.close()
#define WIN32_LEAN_AND_MEAN

#include <windows.h>
#include <httpfilt.h>
#include <tchar.h>

// Returns 0 if doesn't exist, 1 if it is a file, 2 if it is a directory
int inline file_exists(TCHAR const * filename)
{
  WIN32_FIND_DATA fd;
  HANDLE fh = FindFirstFile(filename, &fd);
  if (fh == INVALID_HANDLE_VALUE)
    return 0;
  else
  {
    FindClose(fh);
    return fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY ? 2 : 1;
  }
}

BOOL WINAPI GetFilterVersion(HTTP_FILTER_VERSION * pVer)
{
  pVer->dwFilterVersion = HTTP_FILTER_REVISION;
  pVer->dwFlags = SF_NOTIFY_URL_MAP | SF_NOTIFY_ORDER_DEFAULT;
  return TRUE;
}

DWORD WINAPI HttpFilterProc(PHTTP_FILTER_CONTEXT pfc, DWORD notificationType, LPVOID pn)
{
  switch(notificationType)
  {
    case SF_NOTIFY_URL_MAP:
      HTTP_FILTER_URL_MAP & um = *((HTTP_FILTER_URL_MAP *)pn);

      if (!file_exists(um.pszPhysicalPath))
      {
        size_t pathlen = _tcslen(um.pszPhysicalPath);
        size_t m = pathlen - _tcslen(um.pszURL);
        
        for(size_t i = pathlen - 1; i > m; --i)
        {
          TCHAR c = um.pszPhysicalPath[i];
          if (c == '\\')
          {
            um.pszPhysicalPath[i] = 0;
            int r = file_exists(um.pszPhysicalPath);
            if (r == 1)
              break;
            else
            {
              um.pszPhysicalPath[i] = c;
              if (r == 2) break;
            }
          }
        }
      }  
  }
  return SF_STATUS_REQ_NEXT_NOTIFICATION;
}
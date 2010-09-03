#!/bin/sh

if test "$#" != 2; then
  echo "USAGE: $0 SOURCE-FILE ELX-FILE"
  exit 1
fi

cat <<EOF
<html><head><title>ELX Output Page</title>
<style type="text/css">
  .elx_C { color: firebrick; font-style: italic; }
  .elx_S { color: #bc8f8f; font-weight: bold; }
  .elx_K { color: purple; font-weight: bold }
  .elx_F { color: blue; font-weight: bold; }
  .elx_L { color: blue; font-weight: bold; }
  .elx_M { color: blue; font-weight: bold; }
  .elx_R { color: blue; font-weight: bold; }
</style>
</head>
<body>
EOF

dirname="`dirname $0`"
python2 $dirname/elx_html.py $1 $2

echo "</body></html>"

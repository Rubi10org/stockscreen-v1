#!/bin/zsh
cd -- "${0:A:h}"
if ! command -v python3 >/dev/null; then
  echo "Python 3 wurde nicht gefunden. Python 3 wird für den lokalen Datenserver benötigt."
  read "?Enter zum Schließen …"
  exit 1
fi
python3 server.py --open
result=$?
if (( result != 0 )); then
  echo "Serverstart fehlgeschlagen. Die Fehlermeldung steht oben."
  read "?Enter zum Schließen …"
fi
exit $result

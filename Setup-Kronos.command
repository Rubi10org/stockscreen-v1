#!/bin/zsh
set -eu
cd "${0:A:h}"
python3 -m pip install --target .kronos-bootstrap uv
.kronos-bootstrap/bin/uv python install 3.11 --no-bin --install-dir .kronos-python --cache-dir .kronos-cache/uv
KRONOS_PYTHON=$(find "$PWD/.kronos-python" -type f -name python3.11 -path '*/bin/*' | head -n 1)
if [[ -z "$KRONOS_PYTHON" ]]; then
  print 'Lokaler Python-Interpreter nicht gefunden.'
  exit 1
fi
.kronos-bootstrap/bin/uv venv --allow-existing .kronos-env --python "$KRONOS_PYTHON" --cache-dir .kronos-cache/uv
.kronos-bootstrap/bin/uv pip install --python .kronos-env/bin/python --cache-dir .kronos-cache/uv -r requirements-kronos.lock
.kronos-env/bin/python setup_kronos_models.py
print 'Kronos ist installiert. Datenserver mit python3 server.py --open neu starten.'

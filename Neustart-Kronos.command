#!/bin/zsh
cd -- "${0:A:h}" || exit 1
python3 - <<'PY'
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

port=8766
try:
    with urllib.request.urlopen('http://127.0.0.1:8766/api/health',timeout=3) as response:
        health=json.load(response)
except urllib.error.URLError:
    health=None
if health is not None:
    if health.get('service')!='stockscreen':
        raise SystemExit('Auf Port 8766 läuft ein anderer Dienst. Er wird nicht beendet.')
    pids=subprocess.check_output(['lsof','-t','-iTCP:8766','-sTCP:LISTEN'],text=True).split()
    for pid in pids:os.kill(int(pid),signal.SIGTERM)
    time.sleep(.5)
print('Stockscreen mit aktualisiertem Kronos starten: http://127.0.0.1:8766/positions.html',flush=True)
os.execv(sys.executable,[sys.executable,str(Path.cwd()/'server.py'),'--port',str(port)])
PY

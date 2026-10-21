#!/bin/zsh
cd "$(dirname "$0")" || exit 1
if [[ ! -x .kronos-env/bin/python ]]; then
  print 'Zuerst Setup-Kronos.command ausführen.'
  exit 1
fi
mkdir -p data/research
rm -f data/research/stop
print 'Öffentliche Daten ergänzen, anschließend vollständige Vergleiche. Bereits gespeicherte Fenster werden wiederverwendet. Kann mehrere Stunden dauern.'
.kronos-env/bin/python research.py --collect --profile full --venue both
print 'Lauf beendet. Ergebnisse auf der Kronos-Seite unter Modellvergleich.'
read '?Enter zum Schließen …'

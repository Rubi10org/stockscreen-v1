#!/bin/zsh
cd "$(dirname "$0")" || exit 1
mkdir -p data/research
touch data/research/stop
print 'Pause angefordert. Das aktuelle Prognosefenster wird noch gespeichert.'

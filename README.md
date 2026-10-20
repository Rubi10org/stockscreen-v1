# Stockscreen V1 — ausschließlich echte Binance-Daten

BTC/USDT, ETH/USDT, SOL/USDT, Fetch.ai FET/USDT und XRP/USDT. Keine Schlüssel, Abos oder Zusatzpakete. Python 3.9 oder neuer erforderlich.

## Starten

**Start.command im Projektordner doppelklicken.** Der lokale Python-Datenserver startet und öffnet den Browser automatisch. Das Terminalfenster bleibt während der Benutzung geöffnet. Beenden mit Ctrl+C.

Alternativ im Projektordner:

```sh
python3 server.py --open
```

Adresse: http://127.0.0.1:8765

Die Anwendung muss über diese Adresse geöffnet werden. Stockscreen.html und Vorschau.html enthalten nur noch einen Starthinweis. Die vorherige direkte Binance-Anbindung aus einer HTML-Datei wurde entfernt, weil Browser-/Vorschau-Netzwerkregeln solche Abfragen blockieren können. Demo und Snapshot sind aus dem Produkt entfernt.

## Verbindung prüfen

```sh
python3 server.py --check
```

Dieser Test ruft die Marktliste und aktuelle OHLCV-Daten für alle fünf Märkte direkt bei Binance ab. Erfolg wird nur nach erfolgreichen Antworten aller Märkte gemeldet. In der eingeschränkten Entwicklungsumgebung scheitert dieser echte Test an der DNS-Auflösung; eine funktionierende Live-Verbindung konnte dort nicht bestätigt werden. Ein externer Datenanbieter kann keine 100-Prozent-Verfügbarkeit garantieren.

## Funktionsumfang

- Bitcoin und Fetch.ai sind anfangs ausgewählt; ein bis fünf Märkte sind frei kombinierbar. Der Paar-Scanner erfordert mindestens zwei geladene Märkte.
- Überlagerte OHLC-Kerzen mit fester Coin-Farbe, Legende und Hervorhebung eines Coins. In der Überlagerung: hohle Kerze = gestiegen, gefüllte Kerze = gefallen. Beim Wechsel auf überlagerte Kerzen wird die Prozentskala gewählt; absolute Kurse bleiben wählbar.
- Echte OHLC-Candlesticks oder Linien; überlagert oder getrennt auf einer UI-Seite.
- Echtes Coin-Volumen und USDT-Umsatz pro Kerze, synchronisierte OHLCV-Anzeige am Cursor.
- Umschalter „Zoomen“ / „Messen %“: Ziehen im Messmodus markiert dieselbe Zeitspanne in allen Charts, zeigt Gewinn/Verlust und Start-/Endkurs je Markt, ohne zu zoomen. Messung vom chronologisch früheren zum späteren Schlusskurs, unabhängig von der Ziehrichtung. Laufende Endkerzen sind vorläufig.
- Gemeinsame Zeitachse, fixierbarer Zeitpunkt, Ziehen zum Zoomen, Doppelklick zum Zurücksetzen, Cursor per Pfeiltaste.
- Absolute Kurse oder Prozententwicklung seit sichtbarem Start; freie UTC-Zeiträume und Tages-Presets.
- Intervalle 1m/5m/15m/1h/4h/1d, Pagination bis 5.000 Kerzen pro Markt.
- Live folgt rollierend und fragt alle 15 Sekunden ab. Die laufende Kerze und ihr Volumen sind vorläufig und gekennzeichnet. Kein Tick-Streaming.
- Historische Ansicht: Live ausschalten, Zeitraum einstellen, Vergleich laden.
- Scan über alle Paar-Kombinationen, Gleichlauf/Gegenlauf/Abweichung, Häufigkeit je Paar, Renditekorrelation, Zeitversatzanalyse ±12 Kerzen ab 30 Beobachtungen.
- Nur abgeschlossene, gemeinsame und lückenlose Kerzen im Scanner. Nicht überlappende Scanfenster. Treffer öffnen den Zeitraum im Chart; CSV-Export.
- Wiederholte Abruffehler bzw. Abruflimits pausieren Live. Alte Daten werden als solche markiert. Keine erfundenen Ersatzdaten.

## Berechnungen

Gleichlauf/Gegenlauf erfordern, dass beide absoluten Bewegungen mindestens dem Grenzwert entsprechen. Abweichung erfordert eine Differenz mindestens doppelt so groß wie der Grenzwert; Gleich-/Gegenlauf haben Vorrang. Häufigkeit bezieht sich auf prüfbare Fenster unter dem gewählten Filter. Die stärksten Treffer stehen oben (absolute Differenz plus kleinere absolute Bewegung).

Korrelation wird auf benachbarten Kerzenrenditen ohne Lücken berechnet. Zeitversatz sucht die stärkste absolute Korrelation bei ±12 Kerzen. Die Richtung ist eine historische Zuordnung, keine gesicherte Prognose. Keine Signifikanzprüfung oder Kausalitätsaussage. Der Scanner verwendet den gesamten geladenen Zeitraum unabhängig vom Zoom. Die Prozentbasis im Chart wird dagegen mit dem sichtbaren Zeitraum neu gesetzt.

## Technik und Tests

Der Browser spricht nur mit dem lokalen Server. Dieser nutzt die offiziellen Binance-Hosts data-api.binance.vision und api.binance.com; der zweite Host wird nur bei Netzwerkfehlern versucht. Regionale Sperren und Abruflimits werden nicht durch Hostwechsel umgangen. TLS-Prüfung bleibt aktiv. Keine öffentlichen Drittanbieter-Proxys, Kontodaten oder Handelsfunktionen. Der Server bindet nur an 127.0.0.1.

```sh
python3 -m unittest discover -s tests -v
```

Berechnungs-Tests nutzen unter macOS die vorhandene JavaScriptCore-Systembibliothek. Auf Systemen ohne diese Bibliothek werden diese Tests übersprungen. Die Tests mit simuliertem Transport ersetzen keine erfolgreiche echte Live-Prüfung.

Vollbild: Die Schaltfläche „Vollbild“ öffnet den gesamten Chartbereich inklusive aller ausgewählten Charts und Bedienelemente. Erneut klicken oder Escape drücken beendet Vollbild. Funktioniert in getrennter und überlagerter Ansicht.

## Widerstands-Tool (ersetzt den Bewegungsscanner)

Abschnitt 03 berechnet jetzt Widerstandszonen je Markt, auch für einen einzelnen Coin. Einstellbar sind Bestätigung durch 2/3/5/10 abgeschlossene Kerzen je Seite, maximale Zonenbreite in Prozent und mindestens 2/3/4 bestätigte Hochs. Die Tabelle zeigt Zone in USDT, Abstand zum zuletzt geladenen Kurs, Berührungen und letztes Hoch. „Im Chart“ markiert die Zone, CSV exportiert die Ergebnisse.

Die Historie ist auf den geladenen Zeitraum und das Intervall beschränkt. Laufende Kerzen bestätigen keine Hochs. Lücken werden nicht als Bestätigung verwendet. Ähnliche lokale Hochs werden gruppiert, ohne durch Verkettung die maximale Toleranz zu überschreiten. Hochs unterhalb des letzten Kurses werden nicht als aktive Widerstandszonen angezeigt. Diese heuristischen Zonen sind keine gesicherten Preisgrenzen. Der frühere Paar-/Bewegungsscanner ist in der Oberfläche ersetzt.

Click-Zoom: Im Chart Mausradtaste gedrückt halten und das Rad drehen. Nach oben hineinzoomen, nach unten herauszoomen; nutzt dieselbe Zeit-/Preisskalierung wie Plus/Minus und berücksichtigt separat/synchron. Ohne Mausradtaste bleibt das normale Seitenscrollen erhalten.

## Kronos mit voller öffentlicher Modellgröße

Die Positionsseite `http://127.0.0.1:8765/positions.html` nutzt jetzt
**NeoQuasar/Kronos-base**, 102,3 Millionen Parameter, statt Kronos-small.
Das ist das größte öffentlich bereitgestellte Kronos-Checkpoint der verwendeten
Modellfamilie; Kronos-large ist laut Projekt nicht öffentlich verfügbar.
Quelle: https://huggingface.co/NeoQuasar/Kronos-base

Konfiguration:

- Bis zu **512** echte abgeschlossene Stundenkerzen: voller Kontext von
  Kronos-base. Einzelne fehlende Stunden behalten ihre tatsächlichen Zeitlücken;
  ihre Anzahl ist auf 2 % der Eingaben begrenzt (bei kurzen Eingaben höchstens
  eine). Größere Unterbrechungen begrenzen weiterhin den Kontext. Keine
  synthetischen Kerzen oder verschobenen Zeitstempel. Diese Erweiterung ist
  technisch geprüft, ihre Prognosequalität jedoch nicht nachgewiesen.
  Gespeicherte Bitvavo-EUR-Kerzen ergänzen den frischen Abruf; veraltete
  Eingaben werden weiterhin abgelehnt. Die lokale Mindestlänge beträgt 32.
- Echte OHLC-Preise und Coin-Volumen von Bitvavo EUR. `amount` wird wie im
  Originalprädiktor aus Coin-Volumen × OHLC-Mittel angenähert und als solche
  Näherung ausgewiesen. Fehlende oder inkonsistente Daten werden geprüft.
- **64** generierte 24-Stunden-Szenarien, verarbeitet in Batches von bis zu vier.
  64 ist ein Rechenbudget, keine natürliche Obergrenze und keine Garantie für
  bessere Prognosen. Modell und Tokenizer laufen im Evaluierungsmodus ohne
  Gradienten. Seeds, Batches und Eingabe-Prüfsumme stehen im JSON-Ergebnis.
- CUDA/MPS wird geprüft; sonst CPU mit bis zu acht Threads. GPU-Fehler führen
  zu einem vollständig neu berechneten CPU-Lauf mit ausgewiesenem Hinweis.
  Bei Speichermangel wird die Batchgröße reduziert. Kein stiller Wechsel auf
  ein kleineres Modell.
- Ein Auftrag zurzeit, Laufzeitgrenze **20 Minuten**. Fortschritt wird angezeigt.
  Abbruch wird am nächsten Batch-Übergang berücksichtigt. Live-Kurse und die
  Vergleichsseite bleiben unabhängig vom Modellauftrag bedienbar.

Die Oberfläche zeigt Mittelwert, Median, 10-/90%-Quantile, Minimum/Maximum der
Schlusskurse und formal gültige mittlere OHLC-Kerzen. Das Band ist eine
**Szenarioverteilung, kein kalibriertes Konfidenzintervall**. Zusätzlich werden
Szenario-Häufigkeiten über/unter dem Ausgangskurs und hypothetische Rückgänge
angezeigt; diese sind keine echten Gewinnwahrscheinlichkeiten oder Verlustlimits.
Die ausführliche Tabelle enthält alle 24 Stunden, plus 1/4/8/12/24h-Übersicht.
Die gesamte Prognose einschließlich aller 64 Schlusskurspfade ist als JSON
herunterladbar. Die Prognose-Zeitachse bleibt am tatsächlichen Eingangsschluss
verankert; veraltete Modellrechnungen und zu alte Daten bei Abschluss werden
gekennzeichnet. Keine automatischen Orders.

Ein zusätzlicher historischer Vergleich hält die letzten 24 Kerzen vollständig
aus seinen Modelleingaben zurück, berechnet acht Szenarien und vergleicht MAE,
RMSE und MAPE mit einem konstanten letzten Kurs. Das ist **ein einzelnes Fenster**,
kein statistisch belastbarer Backtest oder Track Record. Eine Überschneidung
mit den Vortrainingsdaten des veröffentlichten Modells wird nicht ausgeschlossen.
Bei weniger als 56 Eingangskerzen wird dieser Vergleich begründet ausgelassen.

Einrichtung auf einem neuen Mac:

```bash
./Setup-Kronos.command
python3 server.py --open
```

Das Setup installiert Python 3.11, Pakete und öffentliche Safetensors-Gewichte für base, small und den Tokenizer
in Projekt-Unterordnern. Versionierte Pakete stehen in `requirements-kronos.lock`.
Der Datenserver selbst bleibt Python-3.9-kompatibel; der Modellprozess verwendet
`.kronos-env/bin/python`. Auf diesem Mac ist die Umgebung bereits eingerichtet.
Die großen Modell-/Cache-Dateien und die Python-Umgebung sind von Git ausgeschlossen.

Originalcode (unverändert mit MIT-Lizenz unter `vendor/kronos_model/`):
https://github.com/shiyu-coder/Kronos, Commit
`67b630e67f6a18c9e9be918d9b4337c960db1e9a`.
Modellrevisionen und Inferenzparameter stehen in `kronos_config.py`.
Für Betrieb werden keine Trading-Schlüssel oder kostenpflichtigen Abos benötigt.

Tests in der eingerichteten Modellumgebung:

```bash
.kronos-env/bin/python -m unittest discover -s tests
```

Verifikation des Ausbaus: **115 Tests** erfolgreich. Ein vollständiger echter
Kronos-base-Lauf mit 512 synthetischen Testkerzen, 64 Prognoseszenarien und
zusätzlichem 24-Stunden-Vergleich lief auf CPU mit 102.310.592 Parametern
in rund 346 Sekunden durch. Das vollständige Ergebnis wurde zusätzlich
durch den JavaScript-Report gerendert. Die Zahlen sind ein technischer
Lasttest, keine gemessene Marktprognosegüte.

Funktionstests prüfen unter anderem Chronologie, gehaltene Zielkurse, Volumen,
Sampling, Quantile, fehlerhafte Daten, Job-Konkurrenz, Abbruch und Fehlerpfade.
Modelltests mit synthetischen Eingaben belegen den technischen Ablauf,
**nicht** die Prognosequalität mit aktuellen Bitvavo-Kursen. Die echte
Bitvavo-Verbindung ist in der Agentenumgebung durch den Netzwerkproxy begrenzt.

## Chronologische Modellvergleiche und echtes Prognosejournal

Auf der Kronos-Seite stehen Datenabdeckung, laufende Studien und später gemessene
Prognosefehler unter **Modellvergleich & Prognosejournal**. Der Status aktualisiert
sich alle 5 Sekunden, ohne neue Prognosen anzufordern. Den Datenserver nach einem
Code-Update neu starten.

Gesichert sind je **8.760 echte Stundenkerzen für BTC/USDT und FET/USDT** aus dem
öffentlichen Binance-Connector, im festgehaltenen Jahreszeitraum bis 20.10.2026.
Die Rohantworten samt SHA-256 und Quellenkennung bleiben lokal erhalten. Das sind
Connector-Importe, keine erfolgreich verifizierten ZIP-Archive: Archivabrufe
wurden hier vom Netzwerkproxy unterbrochen. Bitvavo-EUR-Kerzen werden separat
gesichert; die Jahresabdeckung bleibt wegen Abrufabbrüchen unvollständig. Der
jeweils aktuelle Stand steht auf der Seite. Keine Lückenfüllung oder USDT/EUR-Mischung.

Der vollständige Vergleich prüft **small/base × 32/64/128/256/384/512 Kontextkerzen**
mit je acht Szenarien und 20 nicht überlappenden 24-Stunden-Zielfenstern pro
Konfiguration. Die ersten 60 % der Zeit dienen der Auswahl nach mittlerem MAPE,
die nächsten 20 % der empirischen Bandanpassung, die letzten 20 % dem abschließenden
Test der zuvor ausgewählten Konfiguration. Das sind 280 Berechnungen pro Coin,
560 bei zwei vollständigen Datensätzen. Ein Pilot nutzt nur zwei Fenster pro Phase
und eine eingeschränkte Kontextauswahl; er ist kein Qualitätsnachweis.

Die Kalibrierung erweitert die Szenariobänder an 1/4/12/24 Stunden anhand der
vorherigen Kalibrierungsfenster. Erst danach wird die Abdeckung auf Testfenstern
gemessen. 20 Fenster sind ein Anfang, keine belastbare Gewinngarantie. Zeitliche
Abhängigkeiten und unbekannte Vortrainingsüberschneidungen bleiben bestehen.
Verglichen wird mit der Referenz „letzter Kurs bleibt gleich“. Diese Studie ist
kein Handelsbacktest: Gebühren, Slippage, Finanzierung, Stops und Ausführung
sind nicht in einer Rendite verrechnet. Keine automatischen Änderungen der
Live-Konfiguration; insbesondere keine Übertragung von Binance-Ergebnissen auf Bitvavo.

Ausführung und Fortsetzen (kann mehrere Stunden dauern):

```bash
./Start-Kronos-Forschung.command
```

Pause nach dem aktuellen Fenster:

```bash
./Pause-Kronos-Forschung.command
```

Das Startskript entfernt die Pausenmarkierung, ergänzt öffentliche Daten und
setzt passende Checkpoints fort. Ein Dateilock erlaubt nur einen Vergleichslauf.
Im Terminal: `.kronos-env/bin/python research.py --profile full --venue both`;
`--wait` wartet auf einen bereits laufenden Vergleich. Jeder abgeschlossene
Laufabschnitt liegt atomar unter `data/research/studies/`, Daten unter SQLite,
Status unter `/api/research/status`. Neue Daten außerhalb des festgelegten
Jahreszeitraums verändern einen alten Vergleich nicht. Andere Datenstände,
Modell-/Tokenizerrevisionen oder Inferenzcodes erzeugen eine neue Studie.

Das **Prognosejournal** speichert ab diesem Update erfolgreich bereitgestellte
Bitvavo-Prognosen samt Eingaben. Es bewertet ausschließlich Zielzeiten nach
der Veröffentlichung und nur gegen echte spätere Bitvavo-EUR-Kerzen. Diese
Beobachtungen werden beim normalen Laden der Bitvavo-Historie gesammelt; für
fehlende Beobachtungen wird kein Fehlerwert erfunden. Noch laufende Prognosen
können teilweise ausgewertet sein; die Anzahl wird angezeigt. Historische
Studien und Funktionstests werden nicht als echte Live-Prognosen gezählt.
Ein Server-/Browserstillstand kann die spätere Bewertung verzögern, bis passende
echte Kerzen geladen werden. Das Journal sammelt auch bei geschlossenem Browser
keine automatischen neuen Marktkerzen.

## Öffentliche Bitvavo-Anbindung

Die Oberfläche startet mit **Bitvavo · EUR** und BTC/FET als Vorauswahl.
Die Marktliste prüft, welche der fünf unterstützten EUR-Paare aktuell handelbar sind.
Nicht verfügbare Vorauswahlen werden entfernt. Es werden keine Kontodaten abgerufen,
keine Zugangsdaten benötigt und keine Orders gesendet. Über die Datenquellenauswahl
kann weiterhin zu Binance · USDT gewechselt werden.

Für Bitvavo verwendet der Server das Systemprogramm `curl` (auf macOS vorinstalliert),
mit aktiver Zertifikatsprüfung, 5 Sekunden Verbindungs- und 12 Sekunden Abruflimit.
Es werden keine Zugangsdaten übergeben.

Kerzen und Coin-Volumen stammen aus der öffentlichen Bitvavo REST API und werden
im Live-Modus alle 15 Sekunden aktualisiert. Datenlücken werden nicht aufgefüllt.
Bitvavo liefert Kerzen in absteigender Reihenfolge; der Server sortiert sie und
lädt größere Zeiträume in begrenzten Fenstern nach. EUR-Umsatz wird nur als
**Näherung (Coin-Volumen × Schlusskurs)** angeboten, standardmäßig ist Coin-Volumen aktiv.

Open Interest bleibt eine separat beschriftete **Binance-USD-M-Referenz in USDT**,
keine Bitvavo-Positionsinformation. Binance-Liquidationszonen werden in der
Bitvavo-EUR-Ansicht deaktiviert, um USDT-Preise nicht als EUR darzustellen.
Für diese Zonen zur Binance-Ansicht wechseln. Die Anbindung stellt noch keine
Entry-/Exit-Strategie oder Margin-Kontoanbindung dar.

Nach Änderungen am Server: mit Ctrl+C beenden, `python3 server.py --open` starten
und die Seite mit Cmd+Shift+R neu laden.

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

## Long-/Short-Liquidationen

Die Chart-Leiste enthält den Umschalter **Liquidationen aus / Beobachtete Liquidationen / Geschätzte Liquidationszonen**, auch im Einzel-Vollbild. Long ist rosa, Short türkis. Abschnitt 04 erläutert die Quelle und listet die Bereiche. Nach dem Update muss der Python-Server neu gestartet werden.

**Beobachtet:** Der Server sammelt automatisch öffentliche Binance USD-M `forceOrder`-Snapshots über `wss://fstream.binance.com/market/ws/!forceOrder@arr`. SELL schließt eine Long-Position, BUY schließt eine Short-Position. Verwendet werden ausgeführte Menge `z` und durchschnittlicher Ausführungskurs `ap`, keine ungefüllten Ordermengen. USD-M wird über Symbol und `st` gefiltert. Preisbereiche von 0,2 % werden getrennt je Richtung gruppiert; bis zu drei Bereiche je Coin/Richtung nach gemeldetem Snapshot-Wert. Wiederholte identische Meldungen werden dedupliziert. Da Auftrags-IDs fehlen, sind Snapshot-Summen keine vollständigen oder exakt deduplizierten Börsen-Gesamtvolumina. Insbesondere können Teilfüllungs-Updates kumulierte Mengen enthalten.

Die SQLite-Aufzeichnung liegt unter `data/` und wird nicht in Git hochgeladen. Sie erfasst nur Zeiten, in denen der Server läuft und der Stream verbunden ist; keine historische Rückbefüllung. Aufbewahrung maximal sieben Tage, mit möglichen Datenlücken. Die Anzeige berücksichtigt den geladenen Chartzeitraum, begrenzt auf sieben Tage. Keine Meldungen bedeutet keine gespeicherten Meldungen, nicht null tatsächliche Liquidationen. Die aktuelle öffentliche Binance-Quelle liefert höchstens den letzten Snapshot je Markt/Sekunde. Sie stellt keine Karte der offenen Positionen bereit. Futures-Preise können von den dargestellten Spot-Kursen abweichen.

**Geschätzt:** Vereinfachtes Szenariomodell auf echten historischen Spot-Kerzen. Hypothetische Einstiege am Schlusskurs, gleiche Gewichtung von 10×/25×/50×, Schwellen näherungsweise `Entry × (1 − 1/Leverage)` für Long und `Entry × (1 + 1/Leverage)` für Short. Später erreichte Schwellen werden verworfen. Spot-Umsatz gewichtet die Szenarien; die Intensität ist auf die stärkste Modellzone derselben Richtung und desselben Coins normalisiert. Keine echten Positionsbestände, kein USD-Liquidationsvolumen, keine Maintenance-Margin-/Gebühren-/Cross-Margin-Berechnung, keine kalibrierte Eintrittswahrscheinlichkeit. Es werden nur die stärksten drei Modellbereiche je Richtung gezeigt.

Die verfügbaren CoinGecko-Tools bieten keine Liquidations-Preisereignisse. Das CoinMarketCap-Plugin wurde geprüft und liefert unter anderem globale BTC-Liquidationssummen, aber keine Preiszonen; diese Summen wurden nicht als Zonen zweckentfremdet. ChatGPT-Plugins sind keine aus der lokalen Anwendung dauerhaft aufrufbaren Backends. Neue Anbieter führen deshalb nicht automatisch zu zusätzlichen lokalen API-Zugängen. Der neue Live-Datenpfad nutzt ausschließlich den öffentlichen Binance-Stream, ohne Abo oder API-Schlüssel.

Dokumentation: https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/market

Die Stream-Anbindung ist durch simulierte Frame-/Protokolltests abgesichert (TLS-Handshake, Nachrichtenfragmentierung, maskiertes Pong, Nachrichtenlimits); ein echter erfolgreicher Stream-Empfang konnte in der netzwerkbeschränkten Entwicklungsumgebung nicht bestätigt werden.

## OI-gestütztes Liquidationsmodell (ersetzt das reine Spot-Volumenmodell)

Die aktuelle geschätzte Ansicht nutzt `/futures/data/openInterestHist`, `/fapi/v1/openInterest`, `/fapi/v1/markPriceKlines` und `/fapi/v1/premiumIndex` von Binance USD-M. OI-Verlauf wird zusätzlich separat unter dem Kurschart angezeigt und lässt sich ausschalten. Historische USDT-Werte und aktueller OI in Coin-Einheiten sind mit eigenen Zeitstempeln versehen. OI-Historie wird auf 29 Tage begrenzt, mindestens 5m und automatisch gröber bei großen Datenmengen; keine Auffüllung fehlender Werte. Änderungen bei einzelnen Symbolen verhindern die restlichen Kurscharts nicht.

Netto-OI-Zuwächse werden als mögliche neue Kontrakte auf Long und Short angesetzt; sie beweisen keine bestimmten Einstiege. Bestands-OI zu Beginn bleibt nicht lokalisierbar. Netto-OI-Rückgänge reduzieren die modellierten Bestände proportional. Später vom Markpreis erreichte Schwellen werden verworfen; nach Datenlücken wird der modellierte Bestand zurückgesetzt. Pro Richtung wird nie mehr Kontraktmenge als der aktuell gemessene OI zugeordnet. Long und Short sind die zwei Seiten derselben Kontrakte und dürfen nicht als unabhängiger Gesamt-OI addiert werden.

Vereinfachte Isolated-Margin-Schwellen bei angenommener Maintenance-Margin-Rate von 0,5 %: Long `Entry × (1−1/L)/(1−MMR)`; Short `Entry × (1+1/L)/(1+MMR)`. Keine Gebühren-, Funding-, Risikostufen- oder Cross-Margin-Rekonstruktion. Basisszenario: je 1/3 der möglichen Kontrakte mit 10×/25×/50×. Sensitivitätsszenarien: 60/30/10 % und 10/30/60 %. Preisbereiche sind 0,5 % breit. Fünf stärkste Zonen je Richtung werden gezeigt.

Geschätzter USDT-Betrag je Zone = modellierte Kontraktmenge × geschätzte Liquidationsschwelle. Die Bandbreite ist Minimum/Maximum dieser drei Hebelszenarien für denselben Preisbereich, kein Konfidenzintervall und keine vollständige Unsicherheitsspanne. Die UI nennt die modellierte OI-Abdeckung und den nicht lokalisierbaren Rest. Fehlende OI-/Markpreis-Daten erzeugen keinen Ersatzbetrag. Das Modell ist nicht gegen einen vollständigen Positionsbestand kalibriert und besitzt keine nachgewiesene Coinglass-Gleichwertigkeit. Die früher im README beschriebene reine Spot-Volumen-Gewichtung ist nur noch ein alter Berechnungshelfer und wird nicht mehr in der geschätzten Ansicht benutzt.

Nach Änderungen am Kronos-Datenpfad: `./Neustart-Kronos.command` startet ausschließlich den als Stockscreen erkannten Server auf Port 8766 neu. Danach die Kronos-Seite neu laden und die Prognose erneut anfordern. Ein bereits gezeichnetes Ergebnis wird nicht nachträglich verändert.

Technischer FET-Test der erweiterten Historie: 512 echte gespeicherte Bitvavo-Kerzen über 513 Stunden, eine fehlende Stunde mit unverändertem Zeitstempelabstand. Kronos-base lieferte mit vier Prognose- und vier Rückblickszenarien gültige Ergebnisse in rund 92 Sekunden. Dieser verkleinerte Test verändert das Live-Budget von 64 Szenarien nicht und belegt keine Marktprognosegüte.

## Kurzbewertung und Positionsszenario zur Kronos-Prognose

Unter jeder neu angeforderten Prognose erscheinen eine Median-/Streuungsbewertung
und ein bedingtes Long- oder Short-Szenario. `static/forecast-position.js` hält
Planungsregeln von der Modellinferenz getrennt. Die Entry-Zone bleibt am letzten
Eingabeschluss verankert (±0,2 ATR); der Stop liegt 1,5 ATR in Gegenrichtung.
ATR nutzt 14 echte True Ranges und verlangt dafür 15 lückenlose Stundenkerzen.
Der 24h-Median ergibt Ziel 2; der 12h-Median ergibt Ziel 1, sofern er dazwischen
liegt, sonst die halbe Strecke. Vorgesehen sind 50 % Schließung je Ziel, ein Stop
für die Restposition und ein spätester vollständiger Ausstieg am letzten Zielzeitpunkt.

Die Prüfung verlangt mindestens 128 Eingangskerzen, eine höchstens eine Stunde
alte Rechnung, aktuelle Eingangsdaten und einen höchstens 60 Sekunden alten
Bitvavo-Tickerabruf. Außerhalb der festen Entry-Zone, bei widersprüchlicher
Modellrichtung, fehlendem/schlechterem historischen Vergleich oder einem geplanten
Netto-CRV unter 2:1 erscheint „Abwarten“ mit Begründung. Ein berechenbares, aber
verworfenes Szenario bleibt als solches mit seinen Niveaus sichtbar. Historische
Prüfung bedeutet nur ein einzelnes zurückgehaltenes Fenster, keine validierte Strategie.

Kostenannahmen: 0,25 % Taker und 0,10 % angenommene Slippage je Einstieg/Ausstieg;
0,0023 % je Stunde auf konservativ 100 % des Positionswerts für 24 Stunden als
Leihkostenansatz. Gebührenbasis: https://bitvavo.com/de/fees, geprüft 20.10.2026.
Persönliche Gebühren, Leihasset/-betrag, Margin-Verfügbarkeit und Kapital werden
nicht abgerufen. Es wird keine Positionsgröße oder Hebel vorgegeben. Die bekannte
5-%-Kapitalgrenze und das Tages-/offene Risiko können so nicht automatisch geprüft
werden. Stops garantieren keine Verlustobergrenze. Keine Kontoanbindung oder Orders.

Die Einstiegsprüfung aktualisiert sich mit Livekursen; sie berechnet das Modell
nicht neu. Für diese Erweiterung genügt Neuladen der Seite und Anfordern einer
Prognose; die Änderungen betreffen ausschließlich die Browserdateien.

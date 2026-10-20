"""Local-only Stockscreen server. Python standard library, no account or packages."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock

ROOT = Path(__file__).parent / 'static'
BASE = 'https://data-api.binance.vision/api/v3/'
BASES = (BASE, 'https://api.binance.com/api/v3/')
LAST_SUCCESS = None
LIQUIDATIONS = None
INTERVALS = {'1m':60000, '5m':300000, '15m':900000, '1h':3600000, '4h':14400000, '1d':86400000}
SYMBOLS = ('BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'FETUSDT', 'XRPUSDT')
CACHE = {}
LOCK = Lock()
GATE = Lock()
LAST_REQUEST = 0


def upstream(endpoint, params=None, ttl=30, futures=False):
    global LAST_REQUEST, LAST_SUCCESS
    root = 'https://fapi.binance.com/' if futures else BASE
    url = root + endpoint + ('?' + urllib.parse.urlencode(params) if params else '')
    with LOCK:
        cached = CACHE.get(url)
        if cached and cached[0] > time.monotonic():
            return cached[1]
    # Shared pacing also applies across browser tabs. Never retry rate-limit errors.
    with GATE:
        time.sleep(max(0, .22 - (time.monotonic() - LAST_REQUEST)))
        LAST_REQUEST = time.monotonic()
        failure = None
        for base in ((root,) if futures else BASES):
            request = urllib.request.Request(url.replace(root, base, 1), headers={'User-Agent':'Stockscreen-local/1.0'})
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    result = json.load(response)
                LAST_SUCCESS = int(time.time()*1000)
                break
            except urllib.error.HTTPError:
                # Do not change hosts to evade regional blocks or rate limits.
                raise
            except urllib.error.URLError as error:
                failure = error
        else:
            raise failure
    with LOCK:
        if len(CACHE) > 300:
            CACHE.clear()
        CACHE[url] = (time.monotonic() + ttl, result)
    return result


def read_series(symbol, interval, start, end, live=False):
    step = INTERVALS[interval]
    rows = []
    cursor = start
    while cursor < end:
        batch = upstream('klines', {'symbol':symbol, 'interval':interval, 'startTime':cursor, 'endTime':end-1, 'limit':1000}, ttl=10 if live else 300)
        if not batch:
            break
        # Only completed candles, timestamp denotes candle CLOSE time, exclusive.
        rows.extend({'time':int(r[0])+step, 'open':float(r[1]), 'high':float(r[2]), 'low':float(r[3]), 'close':float(r[4]), 'baseVolume':float(r[5]), 'volume':float(r[7]), 'closed':int(r[0])+step <= int(time.time()*1000)} for r in batch if int(r[0])+step <= min(end, int(time.time()*1000)) or (live and int(r[0]) < end))
        next_cursor = int(batch[-1][0]) + step
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if len(batch) < 1000:
            break
    return {'symbol':symbol, 'points':rows}


OI_PERIODS = {'5m':300000, '15m':900000, '1h':3600000, '4h':14400000, '1d':86400000}

def open_interest_series(symbol, interval, start, end, include_marks=False):
    now=int(time.time()*1000)
    requested_start=start
    start=max(start,now-29*86400000)
    end=min(end,now)
    desired=max(INTERVALS[interval],300000)
    period=next((p for p,step in OI_PERIODS.items() if step>=desired and max(0,end-start)/step<=2000),'1d')
    step=OI_PERIODS[period]
    rows=[]
    cursor=start
    while cursor<end:
        batch=upstream('futures/data/openInterestHist',{'symbol':symbol,'period':period,'startTime':cursor,'endTime':end,'limit':500},ttl=60,futures=True)
        if not batch:
            break
        rows.extend({'time':int(r['timestamp']),'coins':float(r['sumOpenInterest']),'value':float(r['sumOpenInterestValue'])} for r in batch if start<=int(r['timestamp'])<=end)
        next_cursor=int(batch[-1]['timestamp'])+step
        if next_cursor<=cursor:
            break
        cursor=next_cursor
        if len(batch)<500:
            break
    current=upstream('fapi/v1/openInterest',{'symbol':symbol},ttl=60,futures=True)
    result={'symbol':symbol,'period':period,'step':step,'points':rows,'currentCoins':float(current['openInterest']),'currentTime':int(current['time']),'historyClipped':start>requested_start}
    if include_marks:
        premium=upstream('fapi/v1/premiumIndex',{'symbol':symbol},ttl=60,futures=True)
        marks=[]
        cursor=max(0,start-step)
        while cursor<end:
            batch=upstream('fapi/v1/markPriceKlines',{'symbol':symbol,'interval':period,'startTime':cursor,'endTime':end-1,'limit':500},ttl=60,futures=True)
            if not batch:
                break
            marks.extend({'time':int(r[0])+step,'open':float(r[1]),'high':float(r[2]),'low':float(r[3]),'close':float(r[4])} for r in batch if int(r[0])+step<=end)
            next_cursor=int(batch[-1][0])+step
            if next_cursor<=cursor:
                break
            cursor=next_cursor
            if len(batch)<500:
                break
        result.update(marks=marks,markPrice=float(premium['markPrice']),markTime=int(premium['time']))
    return result


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith('/api/'):
            try:
                query = urllib.parse.parse_qs(parsed.query)
                if parsed.path == '/api/health':
                    self.send_json(200, {'service':'stockscreen', 'lastBinanceSuccess':LAST_SUCCESS, 'mode':'live-only'})
                elif parsed.path == '/api/open-interest':
                    symbols=list(dict.fromkeys(query.get('symbols',[''])[0].split(',')))
                    interval=query.get('interval',['1h'])[0]
                    start,end=int(query['start'][0]),int(query['end'][0])
                    if not 1<=len(symbols)<=5 or any(s not in SYMBOLS for s in symbols) or interval not in INTERVALS or start<0 or end<=start:
                        raise ValueError('Ungültige Open-Interest-Anfrage.')
                    results=[]
                    for symbol in symbols:
                        try:
                            results.append(open_interest_series(symbol,interval,start,end,query.get('model',['0'])[0]=='1'))
                        except Exception as error:
                            results.append({'symbol':symbol,'error':'Binance Futures Open Interest nicht verfügbar: '+str(error)[:180],'points':[]})
                    self.send_json(200,results)
                elif parsed.path == '/api/liquidations':
                    symbols=query.get('symbols',[','.join(SYMBOLS)])[0].split(',')
                    start=int(query.get('start',[int(time.time()*1000)-86400000])[0])
                    end=int(query.get('end',[int(time.time()*1000)])[0])
                    if any(symbol not in SYMBOLS for symbol in symbols) or not 0 <= end-start <= 7*86400000:
                        raise ValueError('Liquidationszeitraum: maximal 7 Tage, nur unterstützte Märkte.')
                    if LIQUIDATIONS is None:
                        self.send_json(503,{'error':'Liquidationsdienst nicht gestartet. Server neu starten.'})
                    else:
                        self.send_json(200,LIQUIDATIONS.query(symbols,start,end))
                elif parsed.path == '/api/markets':
                    exchange = upstream('exchangeInfo', {'symbols':json.dumps(SYMBOLS, separators=(',', ':'))}, ttl=3600)
                    markets = [{'symbol':s['symbol'], 'base':s['baseAsset'], 'quote':s['quoteAsset']} for s in exchange['symbols'] if s['symbol'] in SYMBOLS and s['status']=='TRADING' and s.get('isSpotTradingAllowed', False)]
                    self.send_json(200, markets)
                elif parsed.path == '/api/history':
                    symbols = list(dict.fromkeys(query.get('symbols',[''])[0].split(',')))
                    interval = query.get('interval',['1h'])[0]
                    start, end = int(query['start'][0]), int(query['end'][0])
                    live = query.get('live', ['0'])[0] == '1'
                    if interval not in INTERVALS or not 1 <= len(symbols) <= 5 or any(s not in SYMBOLS for s in symbols):
                        raise ValueError('Bitte 1 bis 5 gültige Märkte und ein gültiges Intervall wählen.')
                    if start < 0 or end <= start or (end-start)/INTERVALS[interval] > 5000:
                        raise ValueError('Zeitraum ungültig oder länger als 5.000 Kerzen. Bitte Intervall vergrößern.')
                    with ThreadPoolExecutor(max_workers=3) as pool:
                        data = list(pool.map(lambda s: read_series(s, interval, start, end, live), symbols))
                    self.send_json(200, data)
                else:
                    self.send_json(404, {'error':'Unbekannter Endpunkt.'})
            except (ValueError, KeyError) as error:
                self.send_json(400, {'error':str(error)})
            except urllib.error.HTTPError as error:
                try:
                    detail = json.loads(error.read(4096).decode('utf-8'))
                    reason = str(detail.get('msg', ''))[:500]
                    code = detail.get('code')
                except (ValueError, UnicodeError, AttributeError):
                    reason, code = '', None
                if error.code in (418,429):
                    message = 'Binance begrenzt die Abrufe. Bitte später erneut laden.'
                elif error.code == 400:
                    message = 'Binance hat die Anfrage abgelehnt (HTTP 400).'
                elif error.code == 451:
                    message = 'Binance ist für diesen Standort nicht verfügbar (HTTP 451).'
                else:
                    message = 'Binance-Abruf fehlgeschlagen (HTTP %s).' % error.code
                if reason:
                    message += ' Binance: '+reason
                self.send_json(502, {'error':message, 'binanceCode':code})
            except urllib.error.URLError as error:
                reason = str(error.reason)
                stage = 'DNS-Auflösung' if any(t in reason.lower() for t in ('name', 'nodename', 'resolution')) else 'TLS-Zertifikatsprüfung' if 'CERTIFICATE' in reason else 'Netzwerkverbindung'
                self.send_json(502, {'error':'Binance-Abruf fehlgeschlagen: '+stage+'. Bitte die Verbindung des Rechners prüfen. Keine Ersatzdaten.'})
            except Exception:
                self.send_json(502, {'error':'Binance konnte vom lokalen Datenserver nicht erreicht werden. Internet/DNS/TLS-Verbindung prüfen. Es werden keine Ersatzdaten angezeigt.'})
            return
        route = '/index.html' if parsed.path == '/' else parsed.path
        path = (ROOT / route.lstrip('/')).resolve()
        if ROOT.resolve() not in path.parents or not path.is_file():
            self.send_error(404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', {'.html':'text/html; charset=utf-8','.css':'text/css','.js':'text/javascript','.json':'application/json'}.get(path.suffix,'application/octet-stream'))
        self.end_headers()
        self.wfile.write(body)


def main():
    global LIQUIDATIONS
    import argparse
    import sys
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--open', action='store_true', help='Browser nach erfolgreichem Serverstart öffnen')
    parser.add_argument('--check', action='store_true', help='Echte Binance-Abrufe für alle fünf Märkte prüfen')
    args = parser.parse_args()
    if args.check:
        try:
            exchange=upstream('exchangeInfo', {'symbols':json.dumps(SYMBOLS, separators=(',', ':'))}, ttl=0)
            available={s['symbol'] for s in exchange['symbols'] if s['status']=='TRADING'}
            if not set(SYMBOLS)<=available:
                raise ValueError('Nicht alle fünf Märkte sind aktuell handelbar.')
            now=int(time.time()*1000)
            for symbol in SYMBOLS:
                series=read_series(symbol,'1m',now-240000,now,live=True)
                if len(series['points'])<2:
                    raise ValueError(symbol+': keine ausreichenden aktuellen Kerzen erhalten.')
                print(symbol+': echte OHLCV empfangen',flush=True)
            print('LIVE-CHECK ERFOLGREICH: alle fünf Märkte erreichbar.',flush=True)
            return 0
        except Exception as error:
            print('LIVE-CHECK FEHLGESCHLAGEN: '+str(error),file=sys.stderr,flush=True)
            return 1
    try:
        httpd = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    except OSError as error:
        print('Der lokale Server konnte nicht starten: '+str(error),file=sys.stderr)
        return 1
    from liquidations import Collector
    data_dir=Path(__file__).parent/'data'
    data_dir.mkdir(exist_ok=True)
    LIQUIDATIONS=Collector(data_dir/'liquidations.sqlite3')
    LIQUIDATIONS.start()
    address='http://127.0.0.1:%s' % args.port
    print('Stockscreen läuft auf '+address+' · Beenden mit Ctrl+C',flush=True)
    if args.open:
        import webbrowser
        from threading import Timer
        Timer(.5,lambda:webbrowser.open(address)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if LIQUIDATIONS:
            LIQUIDATIONS.stop.set()
        httpd.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

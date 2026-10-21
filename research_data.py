"""Public market-data archive with provenance and resumable, venue-separated storage."""
import calendar
import contextlib
import csv
import datetime as dt
import hashlib
import io
import json
import math
from pathlib import Path
import sqlite3
import time
import zipfile

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'/'research'
STEP=3600000


class ResearchStore:
    def __init__(self,path=None):
        self.path=Path(path or DATA/'research.sqlite3')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS candles(venue TEXT,symbol TEXT,quote TEXT,time INTEGER,open REAL,high REAL,low REAL,close REAL,base_volume REAL,quote_volume REAL,source TEXT,PRIMARY KEY(venue,symbol,quote,time));
            CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY,venue TEXT,url TEXT,sha256 TEXT,fetched INTEGER,rows INTEGER);
            CREATE TABLE IF NOT EXISTS segments(id TEXT PRIMARY KEY,status TEXT,details TEXT);
            CREATE TABLE IF NOT EXISTS forecasts(id TEXT PRIMARY KEY,venue TEXT,symbol TEXT,quote TEXT,purpose TEXT,created INTEGER,asof INTEGER,result TEXT);
            CREATE TABLE IF NOT EXISTS scores(forecast_id TEXT,time INTEGER,actual REAL,mean REAL,low REAL,high REAL,baseline REAL,PRIMARY KEY(forecast_id,time));
            ''')
    @contextlib.contextmanager
    def connect(self):
        db=sqlite3.connect(str(self.path),timeout=30)
        db.execute('PRAGMA journal_mode=WAL')
        try:
            yield db
            db.commit()
        finally: db.close()
    def ingest(self,venue,symbol,quote,points,source,url='',sha=''):
        rows=[]
        for p in points:
            if p.get('closed') is False: continue
            timestamp=p['time']
            if timestamp%STEP or not all(isinstance(p.get(k),(int,float)) and math.isfinite(p[k]) and p[k]>0 for k in ('open','high','low','close')) or p['low']>min(p['open'],p['close']) or p['high']<max(p['open'],p['close']):
                raise ValueError('Ungültige historische Kerze.')
            base=p.get('baseVolume')
            if not isinstance(base,(int,float)) or not math.isfinite(base) or base<0: raise ValueError('Ungültiges historisches Volumen.')
            quote_volume=p.get('quoteVolume')
            if quote_volume is not None and (not math.isfinite(quote_volume) or quote_volume<0): raise ValueError('Ungültiger Umsatz.')
            rows.append((venue,symbol,quote,int(timestamp),p['open'],p['high'],p['low'],p['close'],base,quote_volume,source))
        with self.connect() as db:
            db.executemany('INSERT OR REPLACE INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?)',rows)
            db.execute('INSERT OR REPLACE INTO sources VALUES (?,?,?,?,?,?)',(source,venue,url,sha,int(time.time()*1000),len(rows)))
        return len(rows)
    def points(self,venue,symbol,quote,start=0,end=2**62):
        with self.connect() as db:
            rows=db.execute('SELECT time,open,high,low,close,base_volume,quote_volume FROM candles WHERE venue=? AND symbol=? AND quote=? AND time>? AND time<=? ORDER BY time',(venue,symbol,quote,start,end)).fetchall()
        return [dict(zip(('time','open','high','low','close','baseVolume','quoteVolume'),r),closed=True) for r in rows]
    def summary(self,venue,symbol,quote,start,end):
        points=self.points(venue,symbol,quote,start,end)
        actual={p['time'] for p in points};expected=list(range(start+STEP,end+1,STEP))
        missing=[t for t in expected if t not in actual]
        longest=run=0;last=None
        for p in points:
            run=run+1 if last is not None and p['time']-last==STEP else 1
            longest=max(longest,run);last=p['time']
        return {'venue':venue,'symbol':symbol,'quote':quote,'candles':len(points),'expected':len(expected),
            'missing':len(missing),'coveragePct':len(points)/len(expected)*100 if expected else 0,
            'longestContiguous':longest,'first':points[0]['time'] if points else None,'last':points[-1]['time'] if points else None,
            'missingTimes':missing[:100]}
    def completed(self,key):
        with self.connect() as db: return db.execute('SELECT status FROM segments WHERE id=?',(key,)).fetchone()==('done',)
    def segment(self,key,status,details):
        with self.connect() as db:db.execute('INSERT OR REPLACE INTO segments VALUES (?,?,?)',(key,status,json.dumps(details)))


def timestamp_ms(value):
    value=int(value)
    if value>=10**15:return value//1000
    if value<10**11:return value*1000
    return value


def binance_rows(rows,start,end):
    points=[]
    for row in rows:
        try:opened=timestamp_ms(row[0])
        except (ValueError,TypeError):continue  # optional CSV header
        closed=opened+STEP
        if start<closed<=end:
            points.append({'time':closed,'open':float(row[1]),'high':float(row[2]),'low':float(row[3]),'close':float(row[4]),
                'baseVolume':float(row[5]),'quoteVolume':float(row[7]),'closed':True})
    return points


def download_archive(symbol,month,start,end,store):
    import requests
    name=symbol+'-1h-'+month+'.zip'
    url='https://data.binance.vision/data/spot/monthly/klines/'+symbol+'/1h/'+name
    folder=DATA/'archives';folder.mkdir(parents=True,exist_ok=True)
    target=folder/name;checksum=folder/(name+'.CHECKSUM')
    if not target.exists() or not checksum.exists():
        response=requests.get(url,timeout=(5,30));response.raise_for_status()
        check=requests.get(url+'.CHECKSUM',timeout=(5,30));check.raise_for_status()
        digest=check.text.split()[0]
        if len(digest)!=64 or hashlib.sha256(response.content).hexdigest()!=digest:raise ValueError('Archiv-Prüfsumme stimmt nicht: '+name)
        target.write_bytes(response.content);checksum.write_text(check.text)
    digest=checksum.read_text().split()[0]
    if hashlib.sha256(target.read_bytes()).hexdigest()!=digest:raise ValueError('Lokales Archiv beschädigt: '+name)
    with zipfile.ZipFile(target) as archive:
        entries=[entry for entry in archive.namelist() if entry.endswith('.csv')]
        if len(entries)!=1:raise ValueError('Unerwartetes Archivformat.')
        with archive.open(entries[0]) as file:points=binance_rows(csv.reader(io.TextIOWrapper(file,encoding='utf-8')),start,end)
    store.ingest('binance',symbol,'USDT',points,url,url,digest)
    return {'symbol':symbol,'month':month,'candles':len(points),'verified':True}


def months(start,end):
    current=dt.datetime.fromtimestamp(start/1000,dt.timezone.utc).replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    cutoff=dt.datetime.fromtimestamp(end/1000,dt.timezone.utc).replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    while current<cutoff:
        yield current.strftime('%Y-%m')
        current=current.replace(year=current.year+1,month=1) if current.month==12 else current.replace(month=current.month+1)


def collect_bitvavo(symbol,start,end,store):
    from server import bitvavo_series
    total=0
    for cursor in reversed(list(range(start,end,1000*STEP))):
        stop=min(end,cursor+1000*STEP);key='bitvavo:'+symbol+':'+str(cursor)+':'+str(stop)
        if store.completed(key):continue
        series=bitvavo_series(symbol,'1h',cursor,stop,False)
        points=series['points'];total+=store.ingest('bitvavo',symbol,'EUR',points,key,'https://api.bitvavo.com/v2/'+symbol.removesuffix('USDT')+'-EUR/candles')
        store.segment(key,'done',{'candles':len(points)})
        print(key+': '+str(len(points))+' Kerzen',flush=True)
    return total


def import_connector_files(store,start,end):
    count=0
    for path in sorted((DATA/'imports').glob('*-year-*.json')):
        raw=path.read_bytes();payload=json.loads(raw)
        count+=store.ingest('binance',payload['symbol'],'USDT',binance_rows(payload['data']['result'],start,end),
            'connector:'+path.name,'Binance public connector',hashlib.sha256(raw).hexdigest())
    return count


def collect(try_bitvavo=True):
    from concurrent.futures import ThreadPoolExecutor,as_completed
    DATA.mkdir(parents=True,exist_ok=True)
    period=DATA/'period.json'
    if period.exists():window=json.loads(period.read_text())
    else:
        end=int(time.time()*1000)//STEP*STEP;window={'start':end-365*24*STEP,'end':end}
        period.write_text(json.dumps(window))
    start,end=window['start'],window['end'];store=ResearchStore();failures=[]
    import_connector_files(store,start,end)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(download_archive,symbol,month,start,end,store) for symbol in ('BTCUSDT','FETUSDT') if store.summary('binance',symbol,'USDT',start,end)['missing'] for month in months(start,end)]
        for future in as_completed(futures):
            try:print(json.dumps(future.result()),flush=True)
            except Exception as error:failures.append(str(error));print('Archivfehler: '+str(error),flush=True)
    for symbol in ('BTCUSDT','FETUSDT'):
        tail=DATA/'imports'/(symbol+'-tail.json')
        if tail.exists():
            raw=tail.read_bytes();payload=json.loads(raw);rows=payload['data']['result']
            store.ingest('binance',symbol,'USDT',binance_rows(rows,start,end),'connector:'+symbol,'Binance public connector',hashlib.sha256(raw).hexdigest())
        if try_bitvavo:
            try:collect_bitvavo(symbol,start,end,store)
            except Exception as error:failures.append('bitvavo '+symbol+': '+str(error));print(failures[-1],flush=True)
    report={'period':window,'created':int(time.time()*1000),'datasets':[store.summary(v,s,q,start,end) for v,q in [('bitvavo','EUR'),('binance','USDT')] for s in ('BTCUSDT','FETUSDT')],'errors':failures}
    (DATA/'data-quality.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2),flush=True)
    return report


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--skip-bitvavo',action='store_true');args=parser.parse_args()
    collect(not args.skip_bitvavo)

"""Background jobs keep heavyweight model inference off the HTTP request path."""
import json
import hashlib
import math
import subprocess
import threading
import time
import uuid
from pathlib import Path

from kronos_config import CONTEXT, MIN_CONTEXT, HORIZON, STEP, SEEDS, MODEL_ID, MODEL_REVISION, MODEL_FOLDER, TIMEOUT
from kronos_history import recent_sparse_context,missing_hours

ROOT=Path(__file__).resolve().parent


def installation_status():
    missing=[]
    if not (ROOT/'.kronos-env'/'bin'/'python').exists(): missing.append('Python-Umgebung')
    for name in (MODEL_FOLDER,'tokenizer'):
        folder=ROOT/'.kronos-models'/name
        if not (folder/'config.json').is_file() or not (folder/'model.safetensors').is_file(): missing.append(name+'-Modellgewichte')
    return {'installed':not missing,'missing':missing,'model':MODEL_ID,'context':CONTEXT,'sampleCount':len(SEEDS),'horizon':HORIZON,'timeoutSeconds':TIMEOUT}


def normalized_history(points):
    data={}
    for p in points:
        if p.get('closed') is False:
            continue
        timestamp=p.get('time')
        if not isinstance(timestamp,(int,float)) or not math.isfinite(timestamp):
            raise ValueError('Ungültiger Kerzenzeitpunkt für Kronos.')
        if not all(math.isfinite(p.get(k,0)) and p.get(k,0)>0 for k in ('open','high','low','close')) or p['low']>min(p['open'],p['close']) or p['high']<max(p['open'],p['close']):
            raise ValueError('Ungültige OHLC-Eingangsdaten für Kronos.')
        if timestamp%STEP!=0:
            raise ValueError('Kerzen sind nicht an vollen UTC-Stunden ausgerichtet.')
        if timestamp in data and any(data[timestamp].get(k)!=p.get(k) for k in ('open','high','low','close','baseVolume')):
            raise ValueError('Widersprüchliche doppelte Stundenkerze. Daten erneut laden.')
        if 'baseVolume' in p and (not isinstance(p['baseVolume'],(int,float)) or not math.isfinite(p['baseVolume']) or p['baseVolume']<0):
            raise ValueError('Ungültiges Coin-Volumen für Kronos.')
        data[timestamp]=p
    return [data[t] for t in sorted(data)]


def validate_history(points, now, allow_sparse=False):
    data=normalized_history(points)[-CONTEXT:]
    if not data: raise ValueError('Keine abgeschlossenen Kerzen für Kronos.')
    if now-data[-1]['time']>STEP+120000 or data[-1]['time']>now:
        raise ValueError('Kronos-Eingangsdaten sind veraltet oder liegen in der Zukunft.')
    # Earlier gaps need not invalidate a sufficiently long recent context.
    start=0
    for i in range(1,len(data)):
        if data[i]['time']-data[i-1]['time']!=3600000:
            start=i
    contiguous=recent_sparse_context(data) if allow_sparse else data[start:]
    if len(contiguous)<MIN_CONTEXT:
        raise ValueError('Nach der letzten Datenlücke liegen nur '+str(len(contiguous))+
            ' zusammenhängende Stundenkerzen vor. Die Anwendung verlangt mindestens '+str(MIN_CONTEXT)+'; keine Kurse werden ergänzt.')
    return contiguous


def recover_history(symbol, reader, points, now, allow_sparse=False):
    data=normalized_history(points)
    gaps=[(a['time'],b['time']-3600000) for a,b in zip(data,data[1:]) if b['time']-a['time']>3600000]
    recovered=0
    expected=now//STEP*STEP
    if data and data[-1]['time']<expected and expected-data[-1]['time']<=24*STEP:
        try:
            retry=reader(symbol,'1h',data[-1]['time'],expected,False)
            old=len(data)
            data=normalized_history(data+retry['points'])
            recovered+=len(data)-old
        except Exception:
            pass
    # Bound additional work; prioritize recent gaps that affect usable context.
    for start,end in gaps[-3:][::-1]:
        if end-start>24*3600000:
            continue
        try:
            retry=reader(symbol,'1h',start,end,False)
            old=len(data)
            data=normalized_history(data+retry['points'])
            recovered+=len(data)-old
        except Exception:
            # Failed retries never become synthetic candles; validate the latest suffix.
            pass
    selected=validate_history(data,now,allow_sparse=allow_sparse)
    return selected,{'contextCandles':len(selected),'recoveredCandles':recovered,
        'excludedEarlierCandles':min(CONTEXT,len(data))-len(selected),'minimumContext':MIN_CONTEXT,'maximumContext':CONTEXT,'contextReduced':len(selected)<CONTEXT,
        'missingHours':missing_hours(selected),'sparseHistory':bool(missing_hours(selected)),
        'contextSpanHours':(selected[-1]['time']-selected[0]['time'])//STEP+1}


class KronosJobs:
    def __init__(self,journal=None):
        self.journal=journal
        self.lock=threading.Lock()
        self.jobs={}
        self.active=None

    def start(self, symbol, reader):
        if symbol not in ('BTCUSDT','FETUSDT'): raise ValueError('Nur BTC oder FET für Kronos.')
        status=installation_status()
        if not status['installed']:
            raise ValueError('Kronos noch nicht installiert: '+', '.join(status['missing'])+'. Setup-Kronos.command ausführen.')
        with self.lock:
            if self.active:
                existing=self.jobs[self.active]
                if existing['symbol']!=symbol: raise ValueError('Eine Kronos-Berechnung läuft bereits. Bitte warten.')
                return dict(existing)
            job_id=uuid.uuid4().hex
            job={'id':job_id,'symbol':symbol,'status':'running','stage':'Bitvavo-Stundenkerzen laden'}
            if len(self.jobs)>=10: self.jobs.pop(next(iter(self.jobs)))
            self.jobs[job_id]=job
            self.active=job_id
        threading.Thread(target=self.run,args=(job_id,symbol,reader),daemon=True).start()
        return dict(job)

    def get(self,job_id):
        with self.lock:
            if job_id not in self.jobs: raise ValueError('Kronos-Auftrag nicht gefunden.')
            job=dict(self.jobs[job_id])
            if job.get('status')=='running' and not job.get('cancelRequested'):
                try:
                    progress=json.loads((ROOT/'data'/'kronos-progress'/(job_id+'.json')).read_text())
                    job['progress']=progress
                    job['stage']=str(progress.get('stage',job['stage']))[:200]
                except (OSError,ValueError):
                    pass
            return job

    def cancel(self,job_id):
        with self.lock:
            if job_id not in self.jobs: raise ValueError('Kronos-Auftrag nicht gefunden.')
            job=self.jobs[job_id]
            if job['status']=='running':
                job.update(cancelRequested=True,stage='Abbruch angefordert · laufender Batch wird beendet')
                marker=ROOT/'data'/'kronos-progress'/(job_id+'.cancel')
                marker.parent.mkdir(parents=True,exist_ok=True)
                marker.write_text('cancel')
            return dict(job)

    def run(self,job_id,symbol,reader):
        try:
            now=int(time.time()*1000)
            series=reader(symbol,'1h',(now//STEP-CONTEXT-32)*STEP,now,False)
            with self.lock: self.jobs[job_id]['stage']='Daten prüfen und fehlende Kerzen erneut laden'
            points,quality=recover_history(symbol,reader,series['points'],int(time.time()*1000),allow_sparse=True)
            quality['cachedCandles']=series.get('cachedCandles',0)
            quality['retrievalWarning']=series.get('retrievalWarning')
            with self.lock: self.jobs[job_id]['stage']='Kronos berechnet '+str(len(SEEDS))+' Szenarien · Fortschritt folgt'
            with self.lock:
                if self.jobs[job_id].get('cancelRequested'):
                    raise RuntimeError('Berechnung abgebrochen.')
            progress=ROOT/'data'/'kronos-progress'/(job_id+'.json')
            progress.parent.mkdir(parents=True,exist_ok=True)
            process=subprocess.run([str(ROOT/'.kronos-env'/'bin'/'python'),str(ROOT/'kronos_worker.py')],
                input=json.dumps({'points':points,'progressPath':str(progress),'allowSparseHistory':True}),capture_output=True,text=True,timeout=TIMEOUT,cwd=str(ROOT))
            try: result=json.loads(process.stdout)
            except ValueError: raise RuntimeError('Kronos-Prozess fehlgeschlagen: '+process.stderr[-500:])
            if process.returncode or result.get('error'): raise RuntimeError(result.get('error','Kronos-Prozess fehlgeschlagen.'))
            if result.get('model')!=MODEL_ID or result.get('modelRevision')!=MODEL_REVISION or result.get('sampleCount')!=len(SEEDS) or result.get('parameters',{}).get('context')!=len(points):
                raise ValueError('Kronos-Modellkennung oder Inferenzparameter stimmen nicht überein.')
            predictions=result.get('points',[])
            if len(predictions)!=HORIZON or any(p.get('time')!=points[-1]['time']+(i+1)*3600000 or
                not all(math.isfinite(p.get(k,0)) and p.get(k,0)>0 for k in ('close','low','high')) or
                not p['low']<=p['close']<=p['high'] for i,p in enumerate(predictions)):
                raise ValueError('Ungültiges Kronos-Prognoseformat; keine Ersatzprognose.')
            paths=result.get('paths',[])
            if len(paths)!=len(SEEDS) or any(len(path)!=HORIZON or not all(isinstance(v,(int,float)) and math.isfinite(v) and v>0 for v in path) for path in paths):
                raise ValueError('Ungültige Kronos-Szenariopfade.')
            for p in predictions:
                if not all(isinstance(p.get(k),(int,float)) and math.isfinite(p[k]) for k in ('median','p10','p90')) or not p['low']<=p['p10']<=p['median']<=p['p90']<=p['high']:
                    raise ValueError('Inkonsistente Kronos-Szenarioquantile.')
                candle=p.get('ohlc',{})
                if not all(isinstance(candle.get(k),(int,float)) and math.isfinite(candle[k]) for k in ('open','high','low','close')) or candle['close']!=p['close']:
                    raise ValueError('Ungültige Kronos-OHLC-Ausgabe.')
                expected_valid=all(v>0 for v in candle.values()) and candle['low']<=min(candle['open'],candle['close']) and candle['high']>=max(candle['open'],candle['close'])
                if p.get('validOHLC') is not expected_valid:
                    raise ValueError('Inkonsistentes Kronos-Kerzenmerkmal.')
            quality['inputAgeMinutes']=round((int(time.time()*1000)-points[-1]['time'])/60000,1)
            quality['staleAtCompletion']=int(time.time()*1000)-points[-1]['time']>STEP+120000
            result['inputHash']=hashlib.sha256(json.dumps(points,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            result['invalidMeanCandles']=sum(not p['validOHLC'] for p in predictions)
            result.update(symbol=symbol,market=symbol.removesuffix('USDT')+'-EUR',quote='EUR',history=points,
                dataQuality=quality,dataAsOf=points[-1]['time'],generatedAt=int(time.time()*1000),horizonHours=HORIZON)
            with self.lock:
                if self.jobs[job_id].get('cancelRequested'):
                    raise RuntimeError('Berechnung abgebrochen.')
                self.jobs[job_id].update(status='done',stage='Berechnet',result=result)
            if self.journal:
                try:self.journal(job_id,result)
                except Exception as error:result.setdefault('warnings',[]).append('Prognosejournal konnte nicht gespeichert werden: '+str(error)[:150])
        except Exception as error:
            with self.lock:
                cancelled=self.jobs[job_id].get('cancelRequested',False)
                self.jobs[job_id].update(status='cancelled' if cancelled else 'error',stage='Abgebrochen' if cancelled else 'Nicht verfügbar',error=str(error)[:1000])
        finally:
            try:
                for suffix in ('.json','.tmp','.cancel'):
                    (ROOT/'data'/'kronos-progress'/(job_id+suffix)).unlink(missing_ok=True)
            except OSError:
                pass
            with self.lock: self.active=None

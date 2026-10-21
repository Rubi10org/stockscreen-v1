"""Record real issued forecasts; score only targets occurring after publication."""
import json
import time
from research_data import ResearchStore


def record_observations(series):
    store=None
    for item in series:
        if item.get('source')!='bitvavo' or not item.get('points'):continue
        if store is None:store=ResearchStore()
        store.ingest('bitvavo',item['symbol'],'EUR',item['points'],'live:'+item['symbol'],'Bitvavo public candles')


def record_forecast(job_id,result):
    store=ResearchStore();record_observations([{'source':'bitvavo','symbol':result['symbol'],'points':result['history']}])
    with store.connect() as db:
        db.execute('INSERT OR IGNORE INTO forecasts VALUES (?,?,?,?,?,?,?,?)',(job_id,'bitvavo',result['symbol'],'EUR','live',result['generatedAt'],result['dataAsOf'],json.dumps(result,allow_nan=False)))
    score_available(store)


def score_available(store=None,now=None):
    store=store or ResearchStore();now=now or int(time.time()*1000)
    with store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS journal_status(id TEXT PRIMARY KEY,complete INTEGER)')
        forecasts=db.execute('SELECT f.id,f.venue,f.symbol,f.quote,f.created,f.result FROM forecasts f LEFT JOIN journal_status s ON f.id=s.id WHERE f.purpose="live" AND coalesce(s.complete,0)=0 ORDER BY f.created LIMIT 100').fetchall()
        for job_id,venue,symbol,quote,created,raw in forecasts:
            result=json.loads(raw);base=result['history'][-1]['close']
            eligible=[p for p in result['points'] if created<p['time']<=now]
            for p in eligible:
                actual=db.execute('SELECT close FROM candles WHERE venue=? AND symbol=? AND quote=? AND time=?',(venue,symbol,quote,p['time'])).fetchone()
                if actual:
                    db.execute('INSERT OR REPLACE INTO scores VALUES (?,?,?,?,?,?,?)',(job_id,p['time'],actual[0],p['close'],p['p10'],p['p90'],base))
            future=[p for p in result['points'] if p['time']>created]
            count=db.execute('SELECT count(*) FROM scores WHERE forecast_id=?',(job_id,)).fetchone()[0]
            if future and now>=future[-1]['time'] and count==len(future):
                db.execute('INSERT OR REPLACE INTO journal_status VALUES (?,1)',(job_id,))


def summary():
    store=ResearchStore();score_available(store)
    with store.connect() as db:
        total=db.execute('SELECT count(*) FROM forecasts WHERE purpose="live"').fetchone()[0]
        completed=db.execute('SELECT count(*) FROM journal_status WHERE complete=1').fetchone()[0]
        rows=db.execute('SELECT actual,mean,low,high,baseline FROM scores').fetchall()
    return {'forecasts':total,'completedForecasts':completed,'scoredTargets':len(rows),
        'mapePct':sum(abs(mean/actual-1)*100 for actual,mean,lo,hi,base in rows)/len(rows) if rows else None,
        'baselineMAPEPct':sum(abs(base/actual-1)*100 for actual,mean,lo,hi,base in rows)/len(rows) if rows else None,
        'scenarioCoveragePct':sum(lo<=actual<=hi for actual,mean,lo,hi,base in rows)/len(rows)*100 if rows else None,
        'note':'Nur nach Veröffentlichung liegende Zielzeiten; laufende Prognosen können teilweise ausgewertet sein. Keine Handelsrendite.'}

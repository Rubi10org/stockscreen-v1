"""Checkpointed chronological comparison. No training and no automatic live-policy changes."""
import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import time
from research_data import DATA,STEP,ResearchStore,collect
from kronos_report import evaluate_paths,quantile

CONFIGS=[{'model':model,'context':context,'samples':8,'id':model+'-'+str(context)}
    for model in ('small','base') for context in (32,64,128,256,384,512)]


def atomic_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value,indent=2,allow_nan=False));temporary.replace(path)


def chronological_windows(points,count,max_context=512):
    if len(points)<max_context+24*3:raise ValueError('Zu wenig Daten für getrennte Vergleichsphasen.')
    start,end=points[0]['time'],points[-1]['time'];span=end-start
    cuts=[start,start+int(span*.6),start+int(span*.8),end+STEP]
    output={}
    for phase,lower,upper in zip(('selection','calibration','test'),cuts,cuts[1:]):
        candidates=[]
        for index in range(max_context,len(points)-23):
            first=points[index]['time'];last=points[index+23]['time']
            if first<lower or last>=upper:continue
            window=points[index-max_context:index+24]
            if all(b['time']-a['time']==STEP for a,b in zip(window,window[1:])):candidates.append(index)
        chosen=[]
        if candidates:
            for n in range(count):
                target=candidates[round(n*(len(candidates)-1)/max(1,count-1))]
                if not chosen or target>=chosen[-1]+24:chosen.append(target)
        if len(chosen)<count:raise ValueError('Phase '+phase+': nur '+str(len(chosen))+' getrennte, lückenlose Fenster verfügbar; benötigt '+str(count)+'.')
        output[phase]=chosen
    return output


def score_forecast(result,actual,base):
    report=evaluate_paths(result['paths'],[p['close'] for p in actual],base)
    horizons={}
    for hour in (1,4,12,24):
        point=result['points'][hour-1];truth=actual[hour-1]['close']
        horizons[str(hour)]={'actual':truth,'mean':point['close'],'median':point['median'],'p10':point['p10'],'p90':point['p90'],
            'absolutePctError':abs(point['close']/truth-1)*100,'baselinePctError':abs(base/truth-1)*100,
            'nonconformity':max(0,point['p10']-truth,truth-point['p90'])/base}
    return {'metrics':report,'horizons':horizons,'base':base}


def aggregate(records):
    if not records:return {'windows':0}
    model=sum(r['score']['metrics']['model']['mapePct'] for r in records)/len(records)
    baseline=sum(r['score']['metrics']['baseline']['mapePct'] for r in records)/len(records)
    return {'windows':len(records),'modelMAPE':model,'baselineMAPE':baseline,
        'wins':sum(r['score']['metrics']['beatsBaselineMAE'] for r in records),
        'skillPct':(1-model/baseline)*100 if baseline else None}


def calibration_margins(records,minimum=20,coverage=.8):
    if len(records)<minimum:return {'available':False,'reason':'Mindestens '+str(minimum)+' getrennte Zielfenster für diese empirische Anpassung erforderlich.','windows':len(records)}
    margins={}
    for h in ('1','4','12','24'):
        values=sorted(r['score']['horizons'][h]['nonconformity'] for r in records)
        rank=min(len(values),math.ceil((len(values)+1)*coverage))
        margins[h]=values[rank-1]
    return {'available':True,'windows':len(records),'targetCoverage':coverage,'margins':margins,
        'note':'Empirische Anpassung aus vergangenen Fenstern; zeitliche Abhängigkeit verhindert eine garantierte zukünftige Abdeckung.'}


def summarize_calibrated_test(records,calibration):
    if not calibration.get('available'):return {'available':False}
    horizons={}
    for h in ('1','4','12','24'):
        hits=[]
        for r in records:
            p=r['score']['horizons'][h];margin=calibration['margins'][h]*r['score']['base']
            hits.append(p['p10']-margin<=p['actual']<=p['p90']+margin)
        horizons[h]={'windows':len(hits),'coveragePct':sum(hits)/len(hits)*100 if hits else None}
    return {'available':True,'horizons':horizons,'note':'Ausschließlich auf bis zur Auswahl ungenutzten Testfenstern gemessen; kein Trading-Ergebnis.'}


def run_study(venue,symbol,quote,count=20,profile='full',contexts=None):
    from kronos_worker import predict
    store=ResearchStore()
    period=json.loads((DATA/'period.json').read_text())
    points=store.points(venue,symbol,quote,period['start'],period['end'])
    configs=[c for c in CONFIGS if contexts is None or c['context'] in contexts]
    max_context=max(c['context'] for c in configs)
    windows=chronological_windows(points,count,max_context)
    from kronos_config import MODEL_REVISION,TOKENIZER_REVISION
    protocol={name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() for name in ('kronos_worker.py','kronos_report.py')}
    fingerprint=hashlib.sha256(json.dumps({'points':points,'count':count,'configs':configs,'version':2,'protocol':protocol,'modelRevision':MODEL_REVISION,'tokenizerRevision':TOKENIZER_REVISION},sort_keys=True).encode()).hexdigest()
    folder=DATA/'studies'/(venue+'-'+symbol+'-'+profile+'-'+fingerprint[:12]);state_path=folder/'state.json'
    if state_path.exists():state=json.loads(state_path.read_text())
    else:
        state={'id':folder.name,'venue':venue,'symbol':symbol,'quote':quote,'profile':profile,'datasetHash':fingerprint,
            'inputCandles':len(points),'period':period,
            'status':'running','windowsPerPhase':count,'plan':windows,'configs':configs,'records':[],
            'created':int(time.time()*1000),'livePolicyChanged':False,'selectionRule':'Kleinster durchschnittlicher MAPE ausschließlich auf Auswahlfenstern.'}
    cache={}
    existing={(r['phase'],r['config'],r['asof']) for r in state['records']}
    progress=folder/'progress.json'
    def cancelled():return (DATA/'stop').exists()
    def execute(phase,config,index):
        cut=points[index-1]['time'];key=(phase,config['id'],cut)
        if key in existing:return
        if cancelled():raise KeyboardInterrupt
        observed=points[index-config['context']:index];actual=points[index:index+24]
        state.update(status='running',stage=phase+' · '+config['id'],updated=int(time.time()*1000))
        atomic_json(state_path,state)
        print(venue,symbol,phase,config['id'],len(state['records'])+1,'Fenster',flush=True)
        result=predict({'points':observed,'research':{'model':config['model'],'samples':config['samples']},'progressPath':str(progress)},cache)
        output_file=folder/(phase+'-'+config['id']+'-'+str(cut)+'.json')
        atomic_json(output_file,result)
        record={'phase':phase,'config':config['id'],'asof':cut,'firstTarget':actual[0]['time'],'lastTarget':actual[-1]['time'],
            'modelRevision':result['modelRevision'],'score':score_forecast(result,actual,observed[-1]['close']),
            'resultFile':output_file.name,'durationSeconds':result['durationSeconds']}
        state['records'].append(record);existing.add(key);atomic_json(state_path,state)
    try:
        for config in configs:
            for index in windows['selection']:execute('selection',config,index)
        ranked=[(aggregate([r for r in state['records'] if r['phase']=='selection' and r['config']==c['id']]),c) for c in configs]
        ranked.sort(key=lambda item:item[0]['modelMAPE'])
        winner=ranked[0][1];state['selected']=winner
        state['ranking']=[dict(config=c['id'],**stats) for stats,c in ranked]
        atomic_json(state_path,state)
        for index in windows['calibration']:execute('calibration',winner,index)
        cal=[r for r in state['records'] if r['phase']=='calibration']
        state['calibration']=calibration_margins(cal)
        atomic_json(state_path,state)
        # Only after configuration and calibration are fixed are final targets evaluated.
        for index in windows['test']:execute('test',winner,index)
        tests=[r for r in state['records'] if r['phase']=='test']
        state['test']=aggregate(tests)
        state['calibratedTest']=summarize_calibrated_test(tests,state['calibration'])
        state.update(status='done',stage='Abgeschlossen',finished=int(time.time()*1000),
            interpretation='Kein Nachweis der Profitabilität. Vortrainingsdaten unbekannt; Ergebnisse nur für diesen Handelsplatz und diese Währung.')
        atomic_json(state_path,state)
        return state
    except KeyboardInterrupt:
        state.update(status='paused',stage='Pausiert; gespeicherte Fenster werden beim Neustart wiederverwendet.');atomic_json(state_path,state);return state
    except Exception as error:
        state.update(status='error',error=type(error).__name__+': '+str(error));atomic_json(state_path,state);raise


def run_suite(profile='full',venues=('bitvavo','binance'),contexts=None,wait=False):
    DATA.mkdir(parents=True,exist_ok=True)
    lock=open(DATA/'runner.lock','w')
    if wait:print('Warte auf freien Vergleichsrunner …',flush=True)
    try:fcntl.flock(lock,fcntl.LOCK_EX if wait else fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise RuntimeError('Ein Vergleichslauf läuft bereits.')
    count=2 if profile=='pilot' else 20
    summary={'status':'running','profile':profile,'started':int(time.time()*1000),'studies':[],'errors':[]}
    path=DATA/'suite.json';atomic_json(path,summary)
    try:
        for venue in venues:
            for symbol in ('BTCUSDT','FETUSDT'):
                quote='EUR' if venue=='bitvavo' else 'USDT'
                try:
                    study=run_study(venue,symbol,quote,count,profile,contexts)
                    summary['studies'].append({k:study.get(k) for k in ('id','venue','symbol','quote','status','selected','test','calibration','calibratedTest')})
                except Exception as error:summary['errors'].append({'venue':venue,'symbol':symbol,'error':str(error)})
                atomic_json(path,summary)
                if (DATA/'stop').exists():summary['status']='paused';return summary
        summary['status']='done' if not summary['errors'] else 'partial'
        summary['finished']=int(time.time()*1000);return summary
    finally:
        atomic_json(path,summary);lock.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--collect',action='store_true');parser.add_argument('--wait',action='store_true',help='Auf Abschluss eines bereits laufenden Vergleichs warten');parser.add_argument('--profile',choices=('pilot','full'),default='full');parser.add_argument('--venue',choices=('bitvavo','binance','both'),default='both');parser.add_argument('--contexts',help='Optionale, komma-getrennte Kontextlängen');args=parser.parse_args()
    if args.collect:collect()
    selected=[int(v) for v in args.contexts.split(',')] if args.contexts else None
    if selected is not None and not selected or selected and any(c not in (32,64,128,256,384,512) for c in selected):raise ValueError('Ungültige Kontextauswahl.')
    report=run_suite(args.profile,('bitvavo','binance') if args.venue=='both' else (args.venue,),selected,args.wait)
    print(json.dumps(report,indent=2),flush=True)

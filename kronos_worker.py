"""Isolated full-capacity Kronos inference and retrospective diagnostics."""
import contextlib
import json
import math
import os
import sys
import time
from pathlib import Path
from kronos_config import (CONTEXT,MIN_CONTEXT,MAX_CONTEXT,HORIZON,STEP,SEEDS,MODEL_ID,
    MODEL_REVISION,MODEL_FOLDER,BATCH_SIZE,VALIDATION_SAMPLES)
from kronos_report import quantile,describe_paths,evaluate_paths
from kronos_history import sparse_history_allowed,missing_hours
ROOT=Path(__file__).resolve().parent


def predict(request,runtime_cache=None):
    import pandas as pd
    import torch
    sys.path.insert(0,str(ROOT/'vendor'/'kronos_model'))
    from model import Kronos,KronosTokenizer,KronosPredictor
    started=time.perf_counter()
    runtime_cache={} if runtime_cache is None else runtime_cache
    research=request.get('research')
    model_id,model_folder,model_revision,seeds=MODEL_ID,MODEL_FOLDER,MODEL_REVISION,SEEDS
    if research:
        choices={'base':(MODEL_ID,MODEL_FOLDER,MODEL_REVISION),'small':('NeoQuasar/Kronos-small','small','901c26c1332695a2a8f243eb2f37243a37bea320')}
        if research.get('model') not in choices or research.get('samples') not in (4,8,16,32,64):
            raise ValueError('Ungültiges Forschungsprofil.')
        model_id,model_folder,model_revision=choices[research['model']]
        seeds=SEEDS[:research['samples']]
    points=request['points']
    sparse_allowed=request.get('allowSparseHistory') is True and not research
    valid_times=sparse_history_allowed(points) if sparse_allowed else not any(p['time']-points[i-1]['time']!=STEP for i,p in enumerate(points) if i)
    if not MIN_CONTEXT<=len(points)<=CONTEXT or not valid_times:
        raise ValueError('Erforderlich: '+str(MIN_CONTEXT)+' bis '+str(CONTEXT)+' zusammenhängende abgeschlossene Stundenkerzen.')
    if any(p.get('closed') is False or not all(isinstance(p.get(k),(int,float)) and math.isfinite(p[k]) and p[k]>0 for k in ('open','high','low','close')) for p in points):
        raise ValueError('Ungültige oder laufende Eingangskerze.')
    volume_available=all(isinstance(p.get('baseVolume'),(int,float)) and math.isfinite(p['baseVolume']) and p['baseVolume']>=0 for p in points)
    if any('baseVolume' in p for p in points) and not volume_available:
        raise ValueError('Coin-Volumen ist unvollständig oder ungültig.')
    frame=pd.DataFrame([{k:p[k] for k in ('open','high','low','close')} for p in points])
    if volume_available:
        frame['volume']=[p['baseVolume'] for p in points]
        exact_amount=all(isinstance(p.get('quoteVolume'),(int,float)) and math.isfinite(p['quoteVolume']) and p['quoteVolume']>=0 for p in points)
        frame['amount']=[p['quoteVolume'] for p in points] if exact_amount else frame['volume']*frame[['open','high','low','close']].mean(axis=1)
    stamps=pd.Series(pd.to_datetime([p['time']-STEP for p in points],unit='ms'))
    future=pd.Series(pd.to_datetime([points[-1]['time']+i*STEP for i in range(HORIZON)],unit='ms'))
    progress_path=Path(request['progressPath']) if request.get('progressPath') else None
    regular_targets=all(b['time']-a['time']==STEP for a,b in zip(points[-HORIZON-1:],points[-HORIZON:]))
    can_validate=not research and len(points)-HORIZON>=MIN_CONTEXT and regular_targets
    total=len(seeds)+(VALIDATION_SAMPLES if can_validate else 0)
    def progress(stage,completed=0):
        if progress_path and progress_path.with_suffix('.cancel').exists():
            raise RuntimeError('Berechnung auf Wunsch abgebrochen.')
        if progress_path:
            temporary=progress_path.with_suffix('.tmp')
            temporary.write_text(json.dumps({'stage':stage,'completed':completed,'total':total,'percent':round(completed/total*100),'elapsedSeconds':round(time.perf_counter()-started,1)}))
            temporary.replace(progress_path)
    progress('Kronos-base und Tokenizer laden')
    cpu_threads=max(1,min(8,os.cpu_count() or 1))
    torch.set_num_threads(cpu_threads)
    warnings=[]
    if missing_hours(points):warnings.append(str(missing_hours(points))+' fehlende Stunden im Eingangskontext; nur echte Kerzen mit ihren ursprünglichen Zeitstempeln. Prognosequalität für diesen lückenbehafteten Kontext ist nicht nachgewiesen.')
    device='cpu'
    if torch.cuda.is_available():
        device='cuda:0'
    elif hasattr(torch.backends,'mps') and torch.backends.mps.is_available():
        try:
            probe=torch.arange(4,dtype=torch.float32,device='mps')
            (probe*probe).sum().item()
            device='mps'
        except RuntimeError as error:
            warnings.append('Apple-GPU-Prüfung fehlgeschlagen; CPU verwendet: '+str(error)[:150])
    def engine_for(target):
        key=(model_folder,target)
        if key not in runtime_cache:
            tokenizer=KronosTokenizer.from_pretrained(str(ROOT/'.kronos-models'/'tokenizer'))
            model=Kronos.from_pretrained(str(ROOT/'.kronos-models'/model_folder))
            tokenizer.eval();model.eval()
            engine=KronosPredictor(model,tokenizer,device=target,max_context=MAX_CONTEXT)
            runtime_cache[key]=(engine,sum(p.numel() for p in model.parameters()))
        return runtime_cache[key]
    batch_log=[]
    batch_size=BATCH_SIZE
    def generate(engine,df,x,y,seeds,offset,label):
        nonlocal batch_size
        outputs=[];index=0
        with torch.inference_mode():
            while index<len(seeds):
                progress(label+' · '+str(index)+'/'+str(len(seeds))+' Szenarien · '+device,offset+index)
                size=min(batch_size,len(seeds)-index)
                torch.manual_seed(seeds[index])
                try:
                    batch=engine.predict_batch([df.copy() for _ in range(size)],[x.copy() for _ in range(size)],
                        [y.copy() for _ in range(size)],pred_len=HORIZON,T=1.0,top_p=.9,sample_count=1,verbose=False)
                except RuntimeError as error:
                    if 'out of memory' in str(error).lower() and size>1:
                        batch_size=max(1,size//2)
                        warnings.append('Speichergrenze: Batchgröße auf '+str(batch_size)+' reduziert.')
                        if device.startswith('cuda'): torch.cuda.empty_cache()
                        elif device=='mps': torch.mps.empty_cache()
                        continue
                    raise
                if len(batch)!=size: raise ValueError('Unvollständige Kronos-Szenarien.')
                for output in batch:
                    rows=[{k:float(row[k]) for k in ('open','high','low','close')} for row in output.to_dict('records')]
                    if len(rows)!=HORIZON or not all(math.isfinite(v) for row in rows for v in row.values()) or not all(row['close']>0 for row in rows):
                        raise ValueError('Ungültige Kronos-Prognosewerte; keine Ersatzwerte.')
                    outputs.append(rows)
                batch_log.append({'stage':label,'offset':index,'seed':seeds[index],'count':size})
                index+=size
                progress(label+' · '+str(index)+'/'+str(len(seeds))+' Szenarien · '+device,offset+index)
        return outputs
    def run(engine):
        paths=generate(engine,frame,stamps,future,seeds,0,'Prognose')
        validation={'available':False,'reason':('Die letzten 24 Zielstunden sind nicht lückenlos; kein Vergleich mit einem anderen Zeitraum.' if not regular_targets else 'Separater Rückblick deaktiviert oder zu wenig Kontext: erforderlich '+str(MIN_CONTEXT+HORIZON)+' Eingangskerzen.')}
        if can_validate:
            try:
                split=len(points)-HORIZON
                historical=generate(engine,frame.iloc[:split].reset_index(drop=True),stamps.iloc[:split].reset_index(drop=True),
                    stamps.iloc[split:].reset_index(drop=True),seeds[:VALIDATION_SAMPLES],len(seeds),'Historischer Vergleich')
                validation=evaluate_paths([[p['close'] for p in path] for path in historical],
                    [p['close'] for p in points[split:]],points[split-1]['close'])
                validation.update(trainingCandles=split,trainingEnd=points[split-1]['time'],
                    firstTargetTime=points[split]['time'],lastTargetTime=points[-1]['time'])
            except RuntimeError:
                raise
            except ValueError as error:
                validation={'available':False,'reason':'Historischer Vergleich fehlgeschlagen: '+str(error)}
        return paths,validation
    try:
        engine,parameters=engine_for(device)
        ohlc_paths,validation=run(engine)
    except RuntimeError as error:
        if device=='cpu' or (progress_path and progress_path.with_suffix('.cancel').exists()): raise
        warnings.append('GPU-Berechnung fehlgeschlagen; kompletter Lauf auf CPU wiederholt: '+str(error)[:200])
        runtime_cache.pop((model_folder,device),None)
        device='cpu';batch_size=BATCH_SIZE;batch_log.clear()
        progress('GPU nicht nutzbar · CPU-Neustart')
        engine,parameters=engine_for(device)
        ohlc_paths,validation=run(engine)
    paths=[[p['close'] for p in path] for path in ohlc_paths]
    predictions=[]
    for i in range(HORIZON):
        values=[p[i] for p in paths]
        mean={k:sum(path[i][k] for path in ohlc_paths)/len(ohlc_paths) for k in ('open','high','low','close')}
        valid=all(v>0 for v in mean.values()) and mean['low']<=min(mean['open'],mean['close']) and mean['high']>=max(mean['open'],mean['close'])
        predictions.append({'time':points[-1]['time']+(i+1)*STEP,'close':mean['close'],'median':quantile(values,.5),
            'p10':quantile(values,.1),'p90':quantile(values,.9),'low':min(values),'high':max(values),'ohlc':mean,'validOHLC':valid})
    progress('Auswertung abgeschlossen',total)
    return {'points':predictions,'paths':paths,'sampleCount':len(seeds),'model':model_id,'modelRevision':model_revision,
        'parameterCount':parameters,'device':device,'cpuThreads':cpu_threads,'durationSeconds':round(time.perf_counter()-started,2),
        'warnings':warnings,'validation':validation,'statistics':describe_paths(paths,points[-1]['close']),
        'invalidMeanCandles':sum(not p['validOHLC'] for p in predictions),
        'input':('OHLC + echtes Coin-Volumen und echter Quote-Umsatz' if exact_amount else 'OHLC + echtes Coin-Volumen; Umsatz aus OHLC-Mittel angenähert') if volume_available else 'OHLC ohne Volumen/Umsatz',
        'parameters':{'context':len(points),'maxContext':MAX_CONTEXT,'predLen':HORIZON,'temperature':1.0,'topP':.9,'topK':0,
            'seeds':list(seeds),'profile':'research' if research else 'live','evaluationMode':True,'batchSize':batch_size,'batches':batch_log}}


if __name__=='__main__':
    try:
        request=json.load(sys.stdin)
        with contextlib.redirect_stdout(sys.stderr): result=predict(request)
        print(json.dumps(result,allow_nan=False))
    except Exception as error:
        print(json.dumps({'error':type(error).__name__+': '+str(error)}))
        sys.exit(1)

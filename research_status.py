"""Read-only summary for the model page, including unfinished checkpointed studies."""
import json
from research_data import DATA
from research_journal import summary


def research_status():
    output={'datasets':[],'studies':[],'journal':summary(),'policy':'Keine Live-Konfiguration wird anhand von Binance-Ergebnissen auf Bitvavo übertragen.'}
    file=DATA/'data-quality.json'
    if file.exists():
        data=json.loads(file.read_text());output.update(datasets=data['datasets'],period=data['period'])
    file=DATA/'suite.json'
    if file.exists():output['suite']=json.loads(file.read_text())
    for file in sorted((DATA/'studies').glob('*/state.json')):
        try:
            study=json.loads(file.read_text())
            item={k:study.get(k) for k in ('id','venue','symbol','quote','profile','inputCandles','period','status','stage','selected','ranking','test','calibration','calibratedTest','error')}
            item['completedWindows']=len(study.get('records',[]))
            item['plannedWindows']=len(study.get('configs',[]))*study.get('windowsPerPhase',0)+2*study.get('windowsPerPhase',0)
            progress=file.parent/'progress.json'
            if progress.exists():item['progress']=json.loads(progress.read_text())
            output['studies'].append(item)
        except (OSError,ValueError):continue
    return output

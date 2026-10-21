"""Descriptive statistics of generated scenarios; no calibrated probabilities."""
import math


def quantile(values,q):
    data=sorted(values)
    if not data: raise ValueError('Keine Szenariowerte.')
    index=(len(data)-1)*q
    lo=math.floor(index);hi=math.ceil(index)
    return data[lo]+(data[hi]-data[lo])*(index-lo)


def describe_paths(paths,base):
    ends=[p[-1] for p in paths]
    drawdowns=[]
    for path in paths:
        peak=base;worst=0
        for value in path:
            peak=max(peak,value)
            worst=min(worst,(value/peak-1)*100)
        drawdowns.append(worst)
    return {'upCount':sum(v>base for v in ends),'downCount':sum(v<base for v in ends),
        'flatCount':sum(v==base for v in ends),'sampleCount':len(paths),
        'terminalMean':sum(ends)/len(ends),'terminalMedian':quantile(ends,.5),
        'terminalP10':quantile(ends,.1),'terminalP90':quantile(ends,.9),
        'lowestClose':min(v for p in paths for v in p),'highestClose':max(v for p in paths for v in p),
        'drawdownMedianPct':quantile(drawdowns,.5),'drawdownWorstPct':min(drawdowns)}


def evaluate_paths(paths,actual,base):
    if not paths or any(len(p)!=len(actual) for p in paths) or not actual:
        raise ValueError('Ungültige Rückblickdaten.')
    mean=[sum(p[i] for p in paths)/len(paths) for i in range(len(actual))]
    def metrics(predicted):
        errors=[p-a for p,a in zip(predicted,actual)]
        return {'mae':sum(abs(e) for e in errors)/len(errors),
            'rmse':math.sqrt(sum(e*e for e in errors)/len(errors)),
            'mapePct':sum(abs(e)/a*100 for e,a in zip(errors,actual))/len(errors)}
    model=metrics(mean);baseline=metrics([base]*len(actual))
    return {'available':True,'windows':1,'samples':len(paths),'periods':len(actual),
        'model':model,'baseline':baseline,'beatsBaselineMAE':model['mae']<baseline['mae'],
        'maeImprovementPct':(1-model['mae']/baseline['mae'])*100 if baseline['mae']>0 else None,
        'actual':actual,'predicted':mean,'baselinePrice':base,
        'scenarioBandCoveragePct':sum(quantile([p[i] for p in paths],.1)<=a<=quantile([p[i] for p in paths],.9) for i,a in enumerate(actual))/len(actual)*100}

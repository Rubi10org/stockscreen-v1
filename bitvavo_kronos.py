"""Persistent, venue-specific real candles for Kronos, with a fresh-data attempt."""
from kronos_service import normalized_history
from research_data import ResearchStore


def cached_history(reader,symbol,interval,start,end,live=False,store=None):
    if interval!='1h':raise ValueError('Kronos-Cache unterstützt nur Stundenkerzen.')
    store=store or ResearchStore()
    cached=store.points('bitvavo',symbol,'EUR',start,end)
    warning=None
    try:
        series=reader(symbol,interval,start,end,live)
        fresh=normalized_history(series['points'])
        store.ingest('bitvavo',symbol,'EUR',fresh,'kronos:'+symbol,'https://api.bitvavo.com/v2/'+symbol.removesuffix('USDT')+'-EUR/candles')
    except (OSError,TimeoutError) as error:
        if not cached:raise
        fresh=[];warning='Bitvavo-Abruf fehlgeschlagen; gespeicherte echte EUR-Kerzen werden auf Aktualität geprüft: '+str(error)[:180]
    fresh_times={p['time'] for p in fresh}
    merged={p['time']:p for p in cached}
    merged.update({p['time']:p for p in fresh})
    return {'source':'bitvavo','quote':'EUR','symbol':symbol,'points':[merged[t] for t in sorted(merged)],
        'cachedCandles':sum(t not in fresh_times for t in merged),'retrievalWarning':warning}

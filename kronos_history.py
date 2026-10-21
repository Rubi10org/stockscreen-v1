"""Bounded sparse input: real timestamps only, never synthetic market candles."""
from kronos_config import STEP


def missing_hours(points):
    return sum((b['time']-a['time'])//STEP-1 for a,b in zip(points,points[1:]))


def sparse_history_allowed(points):
    if not points:return False
    if any(p['time']%STEP for p in points):return False
    if any(b['time']-a['time'] not in (STEP,2*STEP) for a,b in zip(points,points[1:])):return False
    return missing_hours(points)<=max(1,int(len(points)*.02))


def recent_sparse_context(points):
    """Keep the longest recent suffix with only isolated, infrequent missing hours."""
    start=0
    for i in range(1,len(points)):
        if points[i]['time']-points[i-1]['time']>2*STEP:start=i
    result=points[start:]
    while result and not sparse_history_allowed(result):result=result[1:]
    return result

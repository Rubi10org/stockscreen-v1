// Conditional planning scenarios; no order execution or calibrated probabilities.
export function positionPlans(points, zones, options={}) {
 const {risk=1,dailyLoss=0,openRisk=0,leverage=1,capital=0,cost=.5,strategy='trend',step}=options;
 if (![risk,dailyLoss,openRisk,leverage,capital,cost].every(Number.isFinite)||risk<=0||risk>5||dailyLoss<0||openRisk<0||leverage<1||leverage>3||capital<0||cost<0)
  return {error:'Risikowerte prüfen: Risiko > 0 bis 5 %, Hebel 1 bis 3×.',plans:[]};
 const budget=Math.min(risk,5-dailyLoss-openRisk);
 if(budget<=0)return {error:'Tagesbudget ausgeschöpft oder durch offene Positionen gebunden.',plans:[]};
 const p=points.filter(p=>p.closed!==false),last=p.at(-1);
 if(p.length<55||p.some(p=>![p.high,p.low,p.close].every(n=>Number.isFinite(n)&&n>0)))return {error:'Mindestens 55 gültige abgeschlossene Kerzen erforderlich.',plans:[]};
 if(step&&p.slice(-55).some((bar,i,arr)=>i&&bar.time-arr[i-1].time!==step))return {error:'Datenlücken im relevanten Zeitraum: kein Setup.',plans:[]};
 const mean=n=>p.slice(-n).reduce((s,b)=>s+b.close,0)/n,atr=p.slice(-14).reduce((sum,b,i)=>{const prev=p[p.length-15+i];return sum+Math.max(b.high-b.low,Math.abs(b.high-prev.close),Math.abs(b.low-prev.close))},0)/14;
 if(!(atr>0))return {error:'Keine ausreichende Kursschwankung für einen Stop.',plans:[]};
 const prior=p.slice(-21,-1),hi=Math.max(...prior.map(b=>b.high)),lo=Math.min(...prior.map(b=>b.low));
 const plans=['long','short'].map(side=>{
  const long=side==='long';let reason=null;
  if(strategy==='trend'&&(long?mean(20)<=mean(50):mean(20)>=mean(50)))reason='Trendfilter nicht erfüllt (Durchschnitt 20/50).';
  if(strategy==='reversal'&&!(long?last.low<lo&&last.close>lo:last.high>hi&&last.close<hi))reason='Keine abgeschlossene Sweep-und-Rückkehr-Kerze.';
  const entry=strategy==='reversal'?(long?last.high:last.low):(long?hi:lo);
  const stop=long?Math.min(last.low,entry-1.5*atr)-.1*atr:Math.max(last.high,entry+1.5*atr)+.1*atr;
  if(Math.abs(last.close-entry)>3*atr)reason=reason||'Einstieg liegt mehr als 3 ATR vom letzten Schlusskurs entfernt.';
  const distance=Math.abs(entry-stop),unitRisk=distance+entry*cost/100;
  const targets=zones.filter(z=>z.side===(long?'short':'long')&&(long?z.low>entry:z.high<entry))
    .map(z=>({...z,price:long?z.low:z.high})).sort((a,b)=>Math.abs(a.price-entry)-Math.abs(b.price-entry)).slice(0,3)
    .map(z=>({...z,rr:(Math.abs(z.price-entry)-entry*cost/100)/unitRisk,change:(z.price/entry-1)*100}));
  if(!targets.length)reason=reason||'Keine passende Liquidations-Modellzone als Ziel verfügbar.';
  else if(targets[0].rr<2)reason=reason||'Erstes Ziel erreicht nach Kosten kein Verhältnis von 2:1.';
  const notional=capital>0?Math.min(capital*budget/100/(unitRisk/entry),capital*leverage):null;
  return {side,entry,stop,targets,atr,budget,reason,notional,margin:notional===null?null:notional/leverage,
    plannedLoss:notional===null?null:notional*unitRisk/entry,
    state:reason?'Kein Setup':'Bedingtes Szenario · Bestätigung abwarten'};
 });
 return {plans,budget,error:null};
}

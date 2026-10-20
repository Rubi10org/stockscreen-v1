export function align(series) {
  if (!series.length) return {times:[],values:[]};
  const maps=series.map(s=>new Map(s.points.filter(p=>p.close>0&&Number.isFinite(p.close)).map(p=>[p.time,p.close])));
  const times=[...maps[0].keys()].filter(t=>maps.every(m=>m.has(t))).sort((a,b)=>a-b);
  return {times,values:maps.map(m=>times.map(t=>m.get(t)))};
}
export function correlation(a,b) {
  if(a.length<3||a.length!==b.length)return null;
  const avg=x=>x.reduce((s,v)=>s+v,0)/x.length, ma=avg(a),mb=avg(b);
  let n=0,da=0,db=0;
  a.forEach((v,i)=>{n+=(v-ma)*(b[i]-mb);da+=(v-ma)**2;db+=(b[i]-mb)**2});
  return da&&db?Math.max(-1,Math.min(1,n/Math.sqrt(da*db))):null;
}
export function scanPatterns(times,values,window,threshold,step,filter='all') {
  const hits=[],pairs=[];
  for(let a=0;a<values.length;a++)for(let b=a+1;b<values.length;b++){
    const ra=[],rb=[];let tested=0,matched=0;
    for(let i=1;i<times.length;i++)if(times[i]-times[i-1]===step){ra.push(values[a][i]/values[a][i-1]-1);rb.push(values[b][i]/values[b][i-1]-1)}
    for(let i=window;i<times.length;i+=window){
      const first=i-window;
      if(times[i]-times[first]!==window*step)continue;
      tested++;
      const x=(values[a][i]/values[a][first]-1)*100,y=(values[b][i]/values[b][first]-1)*100;
      let type=null;
      if(Math.abs(x-y)>=2*threshold)type='divergence';
      if(Math.min(Math.abs(x),Math.abs(y))>=threshold)type=x*y>0?'same':'opposite';
      if(type&&(filter==='all'||filter===type)){matched++;hits.push({a,b,first,last:i,x,y,type,score:Math.abs(x-y)+Math.min(Math.abs(x),Math.abs(y))})}
    }
    pairs.push({a,b,tested,matched,correlation:correlation(ra,rb),leadLag:lagCorrelation(times,values[a],values[b],step)});
  }
  return {hits:hits.sort((a,b)=>b.score-a.score),pairs};
}

export function lagCorrelation(times,a,b,step,maxLag=12,minSamples=30){
 const index=new Map(times.map((t,i)=>[t,i]));let best=null;
 for(let lag=-maxLag;lag<=maxLag;lag++){
  const x=[],y=[];
  for(let i=1;i<times.length;i++){
   if(times[i]-times[i-1]!==step)continue;
   const j=index.get(times[i]+lag*step);
   if(j===undefined||j===0||times[j]-times[j-1]!==step)continue;
   x.push(a[i]/a[i-1]-1);y.push(b[j]/b[j-1]-1);
  }
  if(x.length<minSamples)continue;
  const r=correlation(x,y);if(r===null)continue;
  if(!best||Math.abs(r)>Math.abs(best.correlation)+1e-10||Math.abs(Math.abs(r)-Math.abs(best.correlation))<1e-10&&Math.abs(lag)<Math.abs(best.lag))best={lag,correlation:r,n:x.length};
 }
 return best;
}

export function resistanceZones(points,wing=3,tolerance=.3,minTouches=2,step=3600000){
 const candles=points.filter(p=>p.closed!==false),current=points.at(-1)?.close;
 if(!current||candles.length<2*wing+1)return [];
 const pivots=[];
 for(let i=wing;i<candles.length-wing;i++){
  const p=candles[i];let valid=Number.isFinite(p.high)&&p.high>0;
  for(let j=1;j<=wing&&valid;j++){
   if(p.time-candles[i-j].time!==step*j||candles[i+j].time-p.time!==step*j||p.high<=candles[i-j].high||p.high<candles[i+j].high)valid=false;
  }
  if(valid)pivots.push({price:p.high,time:p.time});
 }
 const clusters=[];
 for(const pivot of pivots.sort((a,b)=>a.price-b.price)){
  const last=clusters.at(-1);
  if(last&&(pivot.price/last[0].price-1)*100<=tolerance)last.push(pivot);else clusters.push([pivot]);
 }
 return clusters.filter(c=>c.length>=minTouches).map(c=>{
  const low=c[0].price,high=c.at(-1).price,level=c.reduce((s,p)=>s+p.price,0)/c.length;
  return {low,high,level,touches:c.length,first:Math.min(...c.map(p=>p.time)),last:Math.max(...c.map(p=>p.time)),distance:Math.max(0,(low/current-1)*100),inside:current>=low&&current<=high,current};
 }).filter(z=>z.high>=current).sort((a,b)=>a.distance-b.distance);
}

export function strongestResistances(points,step){
 const closed=points.filter(p=>p.closed!==false);
 if(closed.length<9)return [];
 const ranges=closed.map((p,i)=>Math.max(p.high-p.low,i?Math.abs(p.high-closed[i-1].close):0,i?Math.abs(p.low-closed[i-1].close):0)/p.close*100).filter(Number.isFinite).sort((a,b)=>a-b);
 const volatility=Math.max(.1,ranges[Math.floor(ranges.length/2)]||.3),tolerance=Math.max(.15,Math.min(2,volatility*.5));
 const zones=resistanceZones(points,3,tolerance,2,step),averageVolume=closed.reduce((sum,p)=>sum+(p.volume||0),0)/closed.length;
 return zones.map(z=>{
  const touches=closed.map((p,i)=>({p,i})).filter(({p,i})=>i>=3&&i<closed.length-3&&p.high>=z.low&&p.high<=z.high&&[1,2,3].every(j=>p.high>closed[i-j].high&&p.high>=closed[i+j].high&&p.time-closed[i-j].time===j*step&&closed[i+j].time-p.time===j*step));
  const rejection=touches.reduce((sum,{p,i})=>sum+Math.max(0,(p.high-Math.min(...closed.slice(i+1,i+4).map(c=>c.low)))/p.high*100),0)/Math.max(1,touches.length);
  const relativeVolume=averageVolume?touches.reduce((sum,{p})=>sum+(p.volume||0),0)/Math.max(1,touches.length)/averageVolume:1;
  const recency=(z.last-closed[0].time)/Math.max(step,closed.at(-1).time-closed[0].time);
  return {...z,score:z.touches*2+Math.min(5,rejection/volatility)+Math.log1p(relativeVolume)+recency};
 }).sort((a,b)=>b.score-a.score).slice(0,3).map((z,i)=>({...z,rank:i+1}));
}

// Scenario model only. No position inventory, leverage distribution, fees or maintenance margin.
export function estimatedLiquidations(points){
 const data=points.filter(p=>p.closed!==false&&p.close>0),current=points.at(-1)?.close;
 if(data.length<3||!current)return [];
 const low=Array(data.length+1).fill(Infinity),high=Array(data.length+1).fill(-Infinity);
 for(let i=data.length-1;i>=0;i--){low[i]=Math.min(low[i+1],data[i].low);high[i]=Math.max(high[i+1],data[i].high)}
 const bins=new Map(),unit=Math.log1p(.0025);
 for(let i=0;i<data.length;i++){
  const p=data[i];if(!(p.volume>0))continue;
  for(const leverage of [10,25,50])for(const side of ['long','short']){
   const level=p.close*(1+(side==='long'?-1:1)/leverage);
   if(side==='long'&&(low[i+1]<=level||level>=current)||side==='short'&&(high[i+1]>=level||level<=current))continue;
   const key=side+':'+Math.floor(Math.log(level)/unit),bottom=Math.exp(Math.floor(Math.log(level)/unit)*unit);
   if(!bins.has(key))bins.set(key,{side,low:bottom,high:bottom*1.0025,weight:0,kind:'estimated'});
   bins.get(key).weight+=p.volume/3;
  }
 }
 const zones=[];
 for(const side of ['long','short']){
  const ranked=[...bins.values()].filter(z=>z.side===side).sort((a,b)=>b.weight-a.weight);
  const max=ranked[0]?.weight||1;
  zones.push(...ranked.slice(0,3).map(z=>({...z,intensity:z.weight/max})));
 }
 return zones;
}

// OI-constrained cohort model. Net OI increases are hypothetical entries, NOT observed positions.
export function oiLiquidationEstimates(context){
 const empty={zones:[],coverage:{long:0,short:0},unassigned:{long:0,short:0},error:null};
 if(context?.error)return {...empty,error:context.error};
 const points=context?.points||[],marks=context?.marks||[],step=context?.step,current=context?.markPrice;
 if(points.length<3||!marks.length||!(current>0)||!(context.currentCoins>0)||!(step>0))return {...empty,error:'Zu wenig Futures-OI-/Markpreis-Daten für die Modellberechnung.'};
 const markMap=new Map(marks.map(p=>[p.time,p])),priors=[[1/3,1/3,1/3],[.6,.3,.1],[.1,.3,.6]],leverage=[10,25,50],mmr=.005,unit=Math.log1p(.005);
 const results=[];let gaps=0;
 for(let scenario=0;scenario<priors.length;scenario++){
  let cohorts=[];
  for(let i=1;i<points.length;i++){
   const prev=points[i-1],p=points[i],bar=markMap.get(p.time);
   if(!bar||p.time-prev.time!==step){if(scenario===0)gaps++;cohorts=[];continue}
   cohorts=cohorts.filter(c=>c.side==='long'?bar.low>c.level:bar.high<c.level);
   if(p.coins<prev.coins&&prev.coins>0){const survival=p.coins/prev.coins;cohorts.forEach(c=>c.quantity*=survival)}
   const increase=p.coins-prev.coins;
   if(increase>0&&bar.close>0)for(const side of ['long','short'])for(let l=0;l<leverage.length;l++){
    const level=side==='long'?bar.close*(1-1/leverage[l])/(1-mmr):bar.close*(1+1/leverage[l])/(1+mmr);
    cohorts.push({side,level,quantity:increase*priors[scenario][l],entry:bar.close});
   }
  }
  cohorts=cohorts.filter(c=>c.side==='long'?c.level<current:c.level>current);
  // Never assign more contracts to either side than the measured OI supports.
  for(const side of ['long','short']){
   const total=cohorts.filter(c=>c.side===side).reduce((sum,c)=>sum+c.quantity,0),factor=total>context.currentCoins?context.currentCoins/total:1;
   cohorts.filter(c=>c.side===side).forEach(c=>c.quantity*=factor);
  }
  const bins=new Map();
  for(const c of cohorts){const bucket=Math.floor(Math.log(c.level)/unit),key=c.side+':'+bucket;
   if(!bins.has(key)){const low=Math.exp(bucket*unit);bins.set(key,{side:c.side,low,high:low*1.005,quantity:0,estimatedNotional:0})}
   const zone=bins.get(key);zone.quantity+=c.quantity;zone.estimatedNotional+=c.quantity*c.level;
  }
  results.push({bins,cohorts});
 }
 const central=results[0],coverage={},unassigned={};
 for(const side of ['long','short']){const assigned=central.cohorts.filter(c=>c.side===side).reduce((sum,c)=>sum+c.quantity,0);coverage[side]=assigned/context.currentCoins;unassigned[side]=(context.currentCoins-assigned)*current}
 const zones=[];
 for(const side of ['long','short']){
  const list=[...central.bins.entries()].filter(([,z])=>z.side===side).sort((a,b)=>b[1].estimatedNotional-a[1].estimatedNotional),maximum=list[0]?.[1].estimatedNotional||1;
  for(const [key,z] of list.slice(0,5)){const amounts=results.map(r=>r.bins.get(key)?.estimatedNotional||0);zones.push({...z,kind:'estimated',intensity:z.estimatedNotional/maximum,lowNotional:Math.min(...amounts),highNotional:Math.max(...amounts),coverage:coverage[side],asOf:points.at(-1).time})}
 }
 return {zones,coverage,unassigned,gaps,asOf:points.at(-1).time,currentOI:context.currentCoins*current,markPrice:current,period:context.period,historyClipped:context.historyClipped,error:null};
}

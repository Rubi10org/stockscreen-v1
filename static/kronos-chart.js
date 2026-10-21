export function kronosChart(history,price,forecast=[],sampleCount=0){
 const bars=history.slice(-90).filter(p=>[p.time,p.open,p.high,p.low,p.close].every(Number.isFinite));
 if(!bars.length||!(price>0))return '';
 const future=forecast.filter(p=>[p.time,p.close,p.low,p.high].every(Number.isFinite)&&p.time>bars[0].time);
 const values=[price,...bars.flatMap(p=>[p.low,p.high]),...future.flatMap(p=>[p.low,p.high,...(p.validOHLC?[p.ohlc.low,p.ohlc.high]:[])])];
 const lo=Math.min(...values),hi=Math.max(...values),pad=(hi-lo)*.12||price*.01,min=lo-pad,max=hi+pad;
 const first=bars[0].time,last=bars.at(-1).time,end=future.length?Math.max(last,future.at(-1).time):last+24*3600000;
 const x=t=>20+(t-first)/(end-first)*965,y=p=>35+(max-p)/(max-min)*345,f=n=>new Intl.NumberFormat('de-DE',{maximumFractionDigits:5}).format(n);
 const boundary=future.length?Math.max(first,future[0].time-3600000):last;
 let out='<svg class="position-live-svg" viewBox="0 0 1100 445" role="img" aria-label="Historische Bitvavo-Kerzen und separat markierte Kronos-Prognose">';
 out+=`<rect x="${x(boundary)}" y="25" width="${985-x(boundary)}" height="365" fill="#d7f58a06"/><line x1="${x(boundary)}" x2="${x(boundary)}" y1="25" y2="390" stroke="#637c58" stroke-dasharray="4 4"/>`;
 for(let i=0;i<5;i++){const p=max-(max-min)*i/4;out+=`<line x1="15" x2="985" y1="${y(p)}" y2="${y(p)}" stroke="#26303d"/><text x="997" y="${y(p)+4}">${f(p)} €</text>`}
 const width=Math.max(1,Math.min(7,(x(last)-x(first))/Math.max(1,bars.length)*.65));
 for(const p of bars){const color=p.close>=p.open?'#7fdfb8':'#f48b9c';out+=`<line x1="${x(p.time)}" x2="${x(p.time)}" y1="${y(p.high)}" y2="${y(p.low)}" stroke="${color}"/><rect x="${x(p.time)-width/2}" y="${y(Math.max(p.open,p.close))}" width="${width}" height="${Math.max(1,Math.abs(y(p.open)-y(p.close)))}" fill="${color}" opacity="${p.closed===false?.45:1}"/>`}
 if(future.length){
  for(const p of future.filter(p=>p.validOHLC&&p.ohlc)){const c=p.ohlc,xx=x(p.time);out+=`<line x1="${xx}" x2="${xx}" y1="${y(c.high)}" y2="${y(c.low)}" stroke="#d7f58a" opacity=".7"/><rect x="${xx-width/2}" y="${y(Math.max(c.open,c.close))}" width="${width}" height="${Math.max(1,Math.abs(y(c.open)-y(c.close)))}" fill="none" stroke="#d7f58a" opacity=".7"/>`}
  const polygon=[...future.map(p=>`${x(p.time)},${y(p.high)}`),...future.slice().reverse().map(p=>`${x(p.time)},${y(p.low)}`)].join(' ');
  const quantiles=future.filter(p=>Number.isFinite(p.p10)&&Number.isFinite(p.p90));
  if(quantiles.length){const inner=[...quantiles.map(p=>`${x(p.time)},${y(p.p90)}`),...quantiles.slice().reverse().map(p=>`${x(p.time)},${y(p.p10)}`)].join(' ');out+=`<polygon points="${inner}" fill="#d7f58a" fill-opacity=".22"/>`}
  const medians=future.filter(p=>Number.isFinite(p.median));
  if(medians.length)out+=`<path d="${medians.map((p,i)=>(i?'L':'M')+x(p.time)+','+y(p.median)).join(' ')}" fill="none" stroke="#8aaef5" stroke-width="1.6"/>`;
  out+=`<polygon points="${polygon}" fill="#d7f58a" fill-opacity=".15"/><path d="${future.map((p,i)=>(i?'L':'M')+x(p.time)+','+y(p.close)).join(' ')}" fill="none" stroke="#d7f58a" stroke-width="2" stroke-dasharray="7 4"/>`;
  out+=`<text x="${x(boundary)+10}" y="18" style="fill:#d7f58a">KRONOS · ${sampleCount} Szenarien · kein Konfidenzintervall</text>`;
 }
 out+=`<line x1="15" x2="985" y1="${y(price)}" y2="${y(price)}" stroke="#e9bf59" stroke-dasharray="3 3"/><text x="25" y="${y(price)-7}" style="fill:#e9bf59">Letzter Handel ${f(price)} €</text>`;
 const date=t=>new Date(t).toLocaleString('de-DE',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
 return out+`<text x="20" y="420">${date(first)}</text><text x="${x(boundary)}" y="420" text-anchor="middle">Modellstart ${date(boundary)}</text><text x="980" y="420" text-anchor="end">${date(end)}</text></svg>`;
}

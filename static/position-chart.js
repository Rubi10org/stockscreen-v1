// Historical candles plus a distinct future price-zone area; no invented future path.
export function positionChart(points, price, plans=[]) {
 const bars=points.slice(-90).filter(p=>[p.open,p.high,p.low,p.close].every(n=>Number.isFinite(n)&&n>0));
 if(!bars.length||!Number.isFinite(price)||price<=0)return '';
 const active=plans.filter(p=>!p.reason),levels=active.flatMap(p=>[p.entry,p.stop,...p.targets.flatMap(t=>[t.low,t.high])]);
 const lo=Math.min(price,...bars.map(p=>p.low),...levels),hi=Math.max(price,...bars.map(p=>p.high),...levels),pad=(hi-lo)*.12||price*.01;
 const min=lo-pad,max=hi+pad,y=n=>35+(max-n)/(max-min)*345,x=i=>20+i/Math.max(1,bars.length-1)*595;
 const f=n=>new Intl.NumberFormat('de-DE',{maximumFractionDigits:5}).format(n),bw=Math.max(1,Math.min(7,550/bars.length));
 let svg='<svg class="position-live-svg" viewBox="0 0 1100 445" role="img" aria-label="Bitvavo-Kerzen mit aktuellen Kurs und möglichen zukünftigen Zielzonen"><rect x="640" y="25" width="350" height="365" fill="#d7f58a06"/><line x1="640" y1="25" x2="640" y2="390" stroke="#485668" stroke-dasharray="4 4"/>';
 for(let i=0;i<5;i++){const n=max-(max-min)*i/4;svg+=`<line x1="15" x2="990" y1="${y(n)}" y2="${y(n)}" stroke="#26303d"/><text x="1000" y="${y(n)+4}">${f(n)} €</text>`}
 bars.forEach((p,i)=>{const color=p.close>=p.open?'#7fdfb8':'#f48b9c';svg+=`<line x1="${x(i)}" x2="${x(i)}" y1="${y(p.high)}" y2="${y(p.low)}" stroke="${color}"/><rect x="${x(i)-bw/2}" y="${y(Math.max(p.open,p.close))}" width="${bw}" height="${Math.max(1,Math.abs(y(p.open)-y(p.close)))}" fill="${color}" opacity="${p.closed===false?.5:1}"/>`});
 for(const p of active){const label=p.side==='long'?'LONG':'SHORT',color=p.side==='long'?'#7fdfb8':'#8aaef5';
  for(const level of [{price:p.entry,label:label+' Entry',color},{price:p.stop,label:label+' Stop',color:'#f48b9c'}])svg+=`<line x1="640" x2="985" y1="${y(level.price)}" y2="${y(level.price)}" stroke="${level.color}" stroke-dasharray="6 4"/><text x="650" y="${y(level.price)-6}" style="fill:${level.color}">${level.label} ${f(level.price)} €</text>`;
  p.targets.forEach((t,i)=>{svg+=`<rect x="640" y="${y(t.high)}" width="345" height="${Math.max(3,y(t.low)-y(t.high))}" fill="${color}" fill-opacity=".17" stroke="${color}"/><text x="650" y="${y(t.high)-7}" style="fill:${color}">${label} Ziel ${i+1} · ${f(t.low)}–${f(t.high)} €</text>`});
 }
 svg+=`<line x1="15" x2="990" y1="${y(price)}" y2="${y(price)}" stroke="#e9bf59" stroke-dasharray="3 3"/><text x="25" y="${y(price)-7}" style="fill:#e9bf59">Letzter Handel ${f(price)} €</text>`;
 const date=t=>new Date(t).toLocaleString('de-DE',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
 return svg+`<text x="20" y="415">${date(bars[0].time)}</text><text x="445" y="415">${date(bars.at(-1).time)}</text><text x="650" y="415">Möglicher Zielraum · Zeitpunkt offen</text></svg>`;
}

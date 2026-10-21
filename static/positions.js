import {oiLiquidationEstimates} from './analysis.js';
import {positionPlans} from './positions-model.js';
import {positionChart} from './position-chart.js';
const $=id=>document.getElementById(id);
const fmt=new Intl.NumberFormat('de-DE',{maximumFractionDigits:6});
const num=n=>fmt.format(n);
const euro=n=>num(n)+' €';
const escape=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let revision=0,expiresAt=0,liveLoading=false;
const chartData={key:'',points:[],price:null,plans:[]};
const profiles={minutes:{interval:'5m',step:300000,days:7},hours:{interval:'1h',step:3600000,days:29},days:{interval:'4h',step:14400000,days:29}};
const liveKey=()=>$('position-coin').value+':'+$('position-profile').value;
function drawLive(){const markup=positionChart(chartData.points,chartData.price,chartData.plans);if(markup)$('position-live-chart').innerHTML=markup}
function clearAssessment(message){expiresAt=0;chartData.plans=[];$('position-plans').innerHTML='';$('position-recommendation').textContent=message;drawLive()}
async function refreshLive(){
 if(liveLoading||document.hidden||!$('position-live').checked)return;
 const key=liveKey(),symbol=$('position-coin').value,cfg=profiles[$('position-profile').value];liveLoading=true;
 try{
  const now=Date.now(),start=Math.floor((now-100*cfg.step)/cfg.step)*cfg.step;
  const [series,ticker]=await Promise.all([api('/api/history',{source:'bitvavo',symbols:symbol,interval:cfg.interval,start,end:now,live:'1'}),api('/api/price',{source:'bitvavo',symbol})]);
  if(key!==liveKey())return;
  if(series[0]?.source!=='bitvavo'||ticker.source!=='bitvavo'||!(ticker.price>0))throw Error('Ungültige Bitvavo-Kursdaten');
  Object.assign(chartData,{key,points:series[0].points,price:ticker.price});
  $('position-price').textContent=euro(ticker.price);$('position-price-status').textContent='Bitvavo · letzter Handel · abgerufen '+new Date(ticker.retrievedAt).toLocaleTimeString('de-DE')+' · 15s Abruf';
  if(chartData.plans.some(p=>p.side==='long'?ticker.price<=p.stop||ticker.price>=p.targets[0].low:ticker.price>=p.stop||ticker.price<=p.targets[0].high))clearAssessment('Stop- oder erste Zielzone berührt. Vorherige Bewertung verworfen – bitte neu anfordern.');
  drawLive();
 }catch(e){if(key!==liveKey())return;clearAssessment('Live-Abruf fehlgeschlagen. Keine aktuelle Empfehlung verfügbar.');$('position-price-status').textContent='Nicht aktuell · '+e.message}
 finally{liveLoading=false;if(key!==liveKey())refreshLive()}
}

async function api(path,params={}){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),60000);
 try{const response=await fetch(path+'?'+new URLSearchParams(params),{signal:controller.signal,cache:'no-store'});const data=await response.json();if(!response.ok)throw Error(data.error||'Datenabruf fehlgeschlagen.');return data}
 catch(e){if(e.name==='AbortError')throw Error('Zeitüberschreitung beim Datenabruf.');throw e}
 finally{clearTimeout(timer)}
}
function error(message){$('position-error').textContent=message;$('position-error').hidden=!message}
function graphic(plan){
 const levels=[{label:'Entry-Trigger',price:plan.entry,color:'#d7f58a'},{label:'Stop',price:plan.stop,color:'#f48b9c'},...plan.targets.map((t,i)=>({label:'Ziel '+(i+1),price:t.price,color:'#67d9d7'}))];
 const lo=Math.min(...levels.map(l=>l.price)),hi=Math.max(...levels.map(l=>l.price)),y=p=>32+(hi-p)/(hi-lo||1)*200;
 return `<svg class="plan-graphic" viewBox="0 0 500 270" role="img" aria-label="Entry, Stop und modellierte Exit-Ziele"><line x1="18" y1="25" x2="18" y2="240" stroke="#485668"/>${levels.map(l=>`<line x1="18" y1="${y(l.price)}" x2="475" y2="${y(l.price)}" stroke="${l.color}" stroke-dasharray="5 4"/><text x="25" y="${y(l.price)-7}" style="fill:${l.color}">${l.label}</text><text x="475" y="${y(l.price)-7}" text-anchor="end">${euro(l.price)}</text>`).join('')}</svg>`;
}
function render(result, direction){
 $('position-plans').innerHTML=result.plans.filter(p=>direction==='both'||direction===p.side).map(plan=>`<article class="position-card"><h3 class="${plan.side==='long'?'positive':'negative'}">${plan.side==='long'?'↗ LONG':'↘ SHORT'}</h3><div class="plan-status"><strong>${escape(plan.state)}</strong><p>${escape(plan.reason||'Kein aktuelles Einstiegssignal. Die beschriebene Bestätigung muss noch erfolgen.')}</p></div>${plan.reason?'':graphic(plan)}
 <div class="plan-level"><span>Entry-Trigger <small>Planwert · keine Order</small></span><strong>${euro(plan.entry)}</strong></div><div class="plan-level"><span>Stop <small>${num(Math.abs(plan.stop/plan.entry-1)*100)} % Kursabstand</small></span><strong>${euro(plan.stop)}</strong></div>
 ${plan.targets.map((t,i)=>`<div class="plan-level"><span>Ziel ${i+1} · Modellzone<small>${num(t.change)} % · Verhältnis ${num(t.rr)}:1 nach Kosten<br>Liquidationsmodell ≈ ${num(t.estimatedNotional)} USDT</small></span><strong>${euro(t.price)}</strong></div>`).join('')}
 <div class="plan-level"><span>Geplantes Risikobudget</span><strong>${num(plan.budget)} %</strong></div>
 ${plan.notional!==null&&!plan.reason?`<div class="plan-level"><span>Positionswert / Margin<small>Aus Kapital, Stop und Kostenpuffer berechnet</small></span><strong>${euro(plan.notional)} / ${euro(plan.margin)}</strong></div><div class="plan-level"><span>Geplanter Verlust inkl. Puffer</span><strong>${euro(plan.plannedLoss)}</strong></div>`:'<p>Positionsgröße erst bei gültigem Szenario und eingegebenem Handelskapital.</p>'}
 </article>`).join('');
}
$('position-form').addEventListener('input',()=>{revision++;clearAssessment('Eingaben geändert. Aktuelle Bewertung erneut anfordern.');if(chartData.key!==liveKey()){chartData.points=[];chartData.price=null;$('position-live-chart').innerHTML='';$('position-price').textContent='— EUR';refreshLive()}expiresAt=0;$('position-status').textContent='Eingaben geändert';$('position-plans').innerHTML='';$('position-context').textContent='Eingaben geändert. Szenarien neu berechnen.';$('position-asof').textContent='Nicht aktuell';error('')});
$('position-form').onsubmit=async event=>{
 event.preventDefault();const requestRevision=++revision;
 const symbol=$('position-coin').value,profile=$('position-profile').value,config=profiles[profile];
 const options={risk:Number($('position-risk').value),dailyLoss:Number($('position-daily').value),openRisk:Number($('position-open').value),capital:Number($('position-capital').value),leverage:Number($('position-leverage').value),cost:Number($('position-cost').value),strategy:$('position-strategy').value,step:config.step};
 const direction=$('position-direction').value;
 clearAssessment('Aktuelle Bewertung wird angefordert …');$('position-asof').textContent='Noch nicht berechnet';error('');$('position-load').disabled=true;$('position-status').textContent='Server prüfen …';
 try{
  if(options.risk<=0||options.risk>5||options.dailyLoss+options.openRisk>=5)throw Error('Kein Risikobudget: Trade-Risiko muss > 0 bis 5 % sein; Tagesverlust plus offenes Risiko müssen unter 5 % liegen.');
  const health=await api('/api/health');if(!health.sources?.includes('bitvavo'))throw Error('Lokalen Server neu starten: python3 server.py --open');
  const now=Date.now(),start=Math.floor((now-config.days*86400000)/config.step)*config.step;
  $('position-status').textContent='Bitvavo-Kurse und Binance-Modell laden …';
  const results=await Promise.allSettled([
   api('/api/history',{source:'bitvavo',symbols:symbol,interval:config.interval,start,end:now,live:'1'}),
   api('/api/open-interest',{symbols:symbol,interval:config.interval,start,end:now,model:'1'}),
   api('/api/price',{source:'bitvavo',symbol})
  ]);
  if(requestRevision!==revision)return;
  if(results[0].status==='rejected')throw Error('Bitvavo: '+results[0].reason.message);
  const series=results[0].value[0];
  if(series?.source!=='bitvavo'||series.quote!=='EUR')throw Error('Keine bestätigten Bitvavo-EUR-Daten erhalten. Server neu starten.');
  if(results[2].status==='rejected')throw Error('Aktueller Bitvavo-Ticker nicht verfügbar: '+results[2].reason.message);
  const ticker=results[2].value;if(ticker.source!=='bitvavo'||ticker.quote!=='EUR'||Date.now()-ticker.retrievedAt>30000)throw Error('Kein aktueller Bitvavo-Ticker. Server gegebenenfalls neu starten.');
  const points=series.points,current=ticker.price;
  Object.assign(chartData,{key:liveKey(),points,price:current,plans:[]});$('position-price').textContent=euro(current);$('position-price-status').textContent='Bitvavo · letzter Handel · abgerufen '+new Date(ticker.retrievedAt).toLocaleTimeString('de-DE');drawLive();
  if(!(current>0)||now-points.at(-1).time>config.step*2)throw Error('Bitvavo-Kurse fehlen oder sind veraltet. Kein Setup.');
  $('position-context').textContent=series.market+' · letzter geladener Kurs '+euro(current)+' · '+points.length+' Kerzen · '+config.interval;
  if(results[1].status==='rejected')throw Error('Liquidationsmodell nicht verfügbar: '+results[1].reason.message);
  const context=results[1].value[0],model=oiLiquidationEstimates(context);
  if(model.error)throw Error('Kein Setup: '+model.error);
  if(Math.abs(now-context.markTime)>300000||Math.abs(now-model.asOf)>Math.max(config.step*2,900000))throw Error('Futures-Modell veraltet. Kein Setup.');
  const factor=current/model.markPrice;
  const zones=model.zones.map(z=>({...z,low:z.low*factor,high:z.high*factor}));
  const plan=positionPlans(points,zones,options);if(plan.error)throw Error(plan.error);
  render(plan,direction);expiresAt=Date.now()+60000;
  chartData.plans=plan.plans.filter(p=>!p.reason&&(direction==='both'||direction===p.side));drawLive();
  $('position-recommendation').textContent=chartData.plans.length?chartData.plans.map(p=>(p.side==='long'?'Long':'Short')+' beobachten: Entry-Trigger '+euro(p.entry)+', Stop '+euro(p.stop)+', erstes Modellziel '+euro(p.targets[0].price)+'. Einstieg erst nach der beschriebenen Kursbestätigung.').join(' '):'Aktuelle Einschätzung: kein Trade nach diesen Regeln. Gründe stehen in den Positionsszenarien.';

  $('position-context').textContent+=' · modellierter OI-Anteil Long '+num(model.coverage.long*100)+' % / Short '+num(model.coverage.short*100)+' % · übriger OI nicht lokalisierbar.';
  $('position-asof').textContent='Berechnet: '+new Date().toLocaleString('de-DE');$('position-status').textContent='Momentaufnahme · manuell aktualisieren';
 }catch(e){if(requestRevision!==revision)return;error(e.message);$('position-status').textContent='Kein belastbares Setup';clearAssessment('Keine aktuelle Empfehlung: '+e.message)}
 finally{$('position-load').disabled=false}
};

setInterval(()=>{if(expiresAt&&Date.now()>expiresAt){expiresAt=0;revision++;clearAssessment('Bewertung älter als 60 Sekunden. Neue Bewertung anfordern; Live-Kurs läuft weiter.');$('position-asof').textContent='Momentaufnahme abgelaufen';$('position-status').textContent='Neu berechnen erforderlich';error('Die Momentaufnahme ist älter als 60 Sekunden. Vor einer neuen Bewertung die Szenarien erneut berechnen.')}},5000);

$('position-live').onchange=()=>{if($('position-live').checked)refreshLive();else $('position-price-status').textContent='Live-Aktualisierung pausiert · letzter geladener Handelspreis'};
setInterval(refreshLive,15000);
refreshLive();

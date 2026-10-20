import {align,strongestResistances} from './analysis.js';
const $=id=>document.getElementById(id);
const colors=['#d7f58a','#8aaef5','#d69bf5','#efb679','#67d9d7','#f58ca5'];
const steps={'1m':60000,'5m':300000,'15m':900000,'1h':3600000,'4h':14400000,'1d':86400000};
const SYMBOLS=['BTCUSDT','ETHUSDT','SOLUSDT','FETUSDT','XRPUSDT'];
const coinColor=s=>colors[Math.max(0,SYMBOLS.indexOf(s))];
const assetName=s=>s==='FETUSDT'?'Fetch.ai (FET)':s.replace('USDT','');
const state={markets:[],selected:['BTCUSDT','FETUSDT'],series:[],times:[],values:[],mode:'split',dragMode:'pan',panDragging:false,axisRanges:{},chartViews:{},syncZoom:false,syncAxis:{},activeChart:null,middleZoomKey:null,expandedChart:null,chartHeights:{},resizingChart:false,expandedFromFullscreen:false,resistanceSelection:null,axisDragging:false,measurement:null,candles:[],view:null,cursor:null,pinned:false,hits:[],revision:0,busy:false,dirty:false,scanned:false,failures:0,lastSuccess:0,rollingMs:7*86400000,loadedSymbols:[],loadedStart:0,interval:'1h'};
const pct=n=>`${n>=0?'+':''}${n.toFixed(2)} %`;
const priceFormat=new Intl.NumberFormat('de-DE',{maximumFractionDigits:2}),smallPriceFormat=new Intl.NumberFormat('de-DE',{maximumFractionDigits:6});
const money=n=>(Math.abs(n)<1?smallPriceFormat:priceFormat).format(n);
const dateFormat=new Intl.DateTimeFormat('de-DE',{timeZone:'UTC',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'});
const axisDateFormat=new Intl.DateTimeFormat('de-DE',{timeZone:'UTC',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
const date=t=>dateFormat.format(t)+' UTC';
const localInput=t=>new Date(t).toISOString().slice(0,16);
const escape=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function notice(message){$('notice').textContent=message;$('notice').hidden=!message}
function resetScan(){$('chart-resistances').textContent='Widerstände anzeigen';$('chart-resistances').setAttribute('aria-pressed','false');state.hits=[];state.scanned=false;state.resistanceSelection=null;$('pair-summary').innerHTML='';$('scan-results').innerHTML='';$('scan-summary').innerHTML='<span class="muted">Bereit: Widerstandszonen der geladenen Märkte untersuchen.</span>'}
async function proxyApi(path){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),90000);
 try{const r=await fetch(path,{signal:controller.signal,cache:'no-store'});let d;try{d=await r.json()}catch{throw Error('Der lokale Datenserver liefert keine gültige Antwort. Bitte Start.command erneut starten.')}if(!r.ok)throw Error(d.error||'Binance-Abruf fehlgeschlagen.');return d}
 catch(e){if(e instanceof TypeError)throw Error('Der lokale Datenserver ist nicht erreichbar. Bitte Start.command im Projektordner starten und http://127.0.0.1:8765 öffnen.');throw e}
 finally{clearTimeout(timer)}
}
async function api(path){return proxyApi(path)}
function setDates(days){const end=$('auto-live').checked?Math.floor(Date.now()/60000)*60000:Math.floor(Date.now()/steps[$('interval').value])*steps[$('interval').value];state.rollingMs=days*86400000;$('end').value=localInput(end);$('start').value=localInput(end-days*86400000);document.querySelectorAll('[data-days]').forEach(b=>b.classList.toggle('active',Number(b.dataset.days)===days))}
function renderSelected(){
 $('selected').innerHTML=state.selected.map((s,i)=>`<span class="chip"><i class="dot" style="background:${coinColor(s)}"></i>${escape(assetName(s))}<button data-remove="${escape(s)}" aria-label="${escape(s)} entfernen">×</button></span>`).join('');
 $('market-count').textContent=`${state.selected.length} / 5`;
 $('selected').querySelectorAll('button').forEach(b=>b.onclick=()=>{if(state.busy)return;state.selected=state.selected.filter(s=>s!==b.dataset.remove);renderSelected();dirty()});
}
function dirty(){state.dirty=true;$('refresh-status').textContent='Aktualisierung pausiert · Einstellungen übernehmen';if(state.series.length)notice('Auswahl oder Zeitraum geändert. „Vergleich laden“ übernimmt die Einstellungen. Die Charts zeigen noch die zuletzt geladenen Daten.')}
function search(){
 const term=$('market-search').value.trim().toUpperCase();
 const markets=state.markets.filter(m=>!state.selected.includes(m.symbol)&&(m.symbol.includes(term)||m.base.includes(term)||m.quote.includes(term)||assetName(m.symbol).toUpperCase().includes(term)));
 $('search-results').hidden=false;
 $('search-results').innerHTML=markets.slice(0,80).map(m=>`<button data-symbol="${escape(m.symbol)}"><span>${escape(assetName(m.symbol))} <small>/ ${escape(m.quote)}</small></span><small>＋</small></button>`).join('')||`<p>${state.markets.length?'Keine weiteren Märkte gefunden.':'Marktliste nicht geladen. Live-Daten erneut verbinden erneut verbinden.'}</p>`;
 $('search-results').querySelectorAll('button').forEach(b=>b.onclick=()=>{if(state.busy)return;if(state.selected.length>=5){notice('Maximal 5 Märkte pro Vergleich. Entferne zuerst einen Markt.');return}state.selected.push(b.dataset.symbol);renderSelected();$('market-search').value='';$('search-results').hidden=true;dirty()});
}
async function connect(){
 if(state.busy)return;
 state.busy=true;$('live').disabled=true;setLoading(true);
 $('connection').textContent='○ Binance wird verbunden';
 try{const markets=await api('/api/markets');state.markets=markets.filter(m=>SYMBOLS.includes(m.symbol));$('connection').textContent=`● Binance verbunden · ${markets.length} Märkte`;notice('');clearData();state.dirty=false;$('auto-live').checked=true;$('end').disabled=true;setDates(7);}
 catch(e){$('data-badge').textContent=state.series.length?'ALTE DATEN':'KEINE DATEN';state.dirty=true;$('refresh-status').textContent='Offline · keine Aktualisierung';$('connection').textContent='○ Binance offline';notice(e.message);}
 finally{state.busy=false;$('live').disabled=false;setLoading(false)}
 if(!state.dirty)await load();
}
function clearData(){state.measurement=null;$('measurement').hidden=true;state.series=[];state.times=[];state.values=[];state.view=null;state.cursor=null;state.pinned=false;$('data-badge').textContent='KEINE DATEN';$('data-badge').classList.remove('stale');$('asset-cards').innerHTML='';$('asset-cards')._markup=null;$('chart-area').innerHTML='<div class="empty"><span class="empty-icon">⌁</span><h3>Dein Vergleich beginnt hier.</h3><p>Wähle Märkte und lade einen Zeitraum.</p></div>';$('coverage').textContent='';resetScan()}
function setLoading(loading){$('load').disabled=loading;$('load').textContent=loading?'Daten werden geladen …':'Vergleich laden ↗';$('scan').disabled=loading||state.series.length<1;$('market-search').disabled=loading;$('browse').disabled=loading;}
async function load(refresh=false){
 if(state.busy)return;
 const following=$('auto-live').checked;
 if(following){const end=Date.now();if(refresh){$('start').value=localInput(end-state.rollingMs)}$('end').value=localInput(end)}
 const start=Date.parse($('start').value+'Z'),end=following?Date.now():Date.parse($('end').value+'Z'),interval=$('interval').value;
 const oldView=state.view&&state.view.map(i=>state.times[i]),oldCursor=state.cursor===null?null:state.times[state.cursor],oldPinned=state.pinned,hadScan=state.scanned;
 if(state.selected.length<1){notice('Bitte mindestens einen Markt auswählen.');return}
 if(!Number.isFinite(start)||!Number.isFinite(end)||end<=start||end>Date.now()+60000){notice('Bitte einen gültigen Zeitraum in der Vergangenheit wählen.');return}
 if((end-start)/steps[interval]>5000){notice('Dieser Zeitraum enthält mehr als 5.000 Kerzen. Bitte ein größeres Intervall oder einen kürzeren Zeitraum wählen.');return}
 state.busy=true;setLoading(true);$('live').disabled=true;notice('');
 try{
 const series=await api('/api/history?'+new URLSearchParams({symbols:state.selected.join(','),interval,start,end,live:following?'1':'0'}));
 const aligned=align(series);
 if(aligned.times.length<3)throw Error('Weniger als 3 gemeinsame abgeschlossene Kerzen. Bitte Zeitraum vergrößern oder andere Märkte wählen.');
 if(!refresh){state.measurement=null;state.axisRanges={};state.chartViews={};state.syncAxis={};}state.series=series;state.times=aligned.times;state.values=aligned.values;state.candles=series.map(s=>{const map=new Map(s.points.map(p=>[p.time,p]));return aligned.times.map(t=>map.get(t))});state.interval=interval;state.view=[0,state.times.length-1];state.cursor=null;state.pinned=false;state.dirty=false;state.failures=0;state.lastSuccess=Date.now();state.loadedSymbols=series.map(s=>s.symbol);state.loadedStart=start;state.rollingMs=end-start;
 if(refresh&&oldView&&oldView[1]<state.times.at(-2)){state.view=oldView.map(nearestTime);if(state.view[0]>=state.view[1])state.view=[0,state.times.length-1]}if(refresh&&oldPinned&&oldCursor>=state.times[0]&&oldCursor<=state.times.at(-1)){state.cursor=nearestTime(oldCursor);state.pinned=true}
 $('refresh-status').textContent=(following?'Live · ':'Geladen · ')+new Date().toLocaleTimeString('de-DE')+(following?' · 15s Aktualisierung':'');
 $('connection').textContent=following?'● Binance LIVE · 15s':'● Binance · Historie';
 $('data-badge').textContent=following?'BINANCE · LIVE 15s':'BINANCE · HISTORISCH';
 $('chart-subtitle').textContent=`${date(state.times[0])} — ${date(state.times.at(-1))} · ${interval}-Kerzen`;
 $('coverage').textContent=`${state.times.length.toLocaleString('de-DE')} gemeinsame Kerzen · alle Zeiten UTC`;
 if(series.some(s=>s.points.length!==state.times.length))notice('Nur gemeinsame Kerzen aller Märkte werden verglichen. Datenlücken werden nicht aufgefüllt.');
 const volumeChoice=$('volume-market').value;$('volume-market').innerHTML=series.map((s,i)=>`<option value="${i}">${escape(s.symbol)}</option>`).join('');if(refresh&&volumeChoice)$('volume-market').value=volumeChoice;resetScan();renderCharts();renderCards();if(hadScan)runScan(false);
 }catch(e){$('data-badge').textContent=state.series.length?'ALTE DATEN':'KEINE DATEN';state.failures++;$('connection').textContent='○ Verbindung unterbrochen · alte Daten';$('refresh-status').textContent='Datenstand unverändert · Abruf fehlgeschlagen';if(state.failures>=3||/limit|begrenzt/i.test(e.message)){$('auto-live').checked=false;$('end').disabled=false;$('refresh-status').textContent='Live wegen Abruffehlern pausiert · erneut verbinden';}notice(e.name==='AbortError'?'Zeitüberschreitung. Bitte kürzeren Zeitraum wählen oder erneut versuchen.':e.message)}
 finally{state.busy=false;setLoading(false);$('live').disabled=false}
}
function marketInfo(symbol){return state.markets.find(m=>m.symbol===symbol)||{base:symbol,quote:''}}
function candleDetails(k,i){const p=state.candles[k][i],m=marketInfo(state.series[k].symbol);return `<div class="ohlc"><span class="candle-status ${p.closed===false?'forming':'closed'}">${p.closed===false?'Laufende Kerze · vorläufig':'Abgeschlossene Kerze'}</span>O ${money(p.open)} · H ${money(p.high)}<br>L ${money(p.low)} · C ${money(p.close)}</div><div class="volume-readout">Vol ${money(p.baseVolume)} ${escape(m.base)}<br>Umsatz ${money(p.volume)} ${escape(m.quote)}</div>`}
function volumeBars(group,w,a,b){
 const k=state.mode==='overlay'?Number($('volume-market').value||0):group[0],base=$('volume-unit').value==='base',field=base?'baseVolume':'volume',points=state.candles[k].slice(a,b+1);
 const max=Math.max(...points.map(p=>p[field]),0),bw=Math.max(.5,Math.min(12,(w-87)/(b-a+1)*.65)),m=marketInfo(state.series[k].symbol);
 let out=`<line x1="14" x2="${w-73}" y1="222" y2="222" stroke="#26303d"/><text x="14" y="237">Vol ${escape(state.series[k].symbol)} · ${escape(base?m.base:m.quote)}</text><text x="${w-63}" y="249">${max>=1e6?(max/1e6).toFixed(1)+'M':max>=1000?(max/1000).toFixed(1)+'K':money(max)}</text>`;
 for(let i=a;i<=b;i++){const p=state.candles[k][i],h=max?p[field]/max*38:0;out+=`<rect x="${xFor(i,w,[a,b])-bw/2}" y="${282-h}" width="${bw}" height="${h}" fill="${p.close>=p.open?'#7fdfb8':'#f48b9c'}" opacity=".55"/>`}
 return out;
}
let cursorFrame=null,chartFrame=null;
function scheduleCursorRender(){if(cursorFrame!==null)return;cursorFrame=requestAnimationFrame(()=>{cursorFrame=null;if(!state.times.length)return;updateCursor();renderCards()})}
function scheduleChartRender(){if(chartFrame!==null)return;chartFrame=requestAnimationFrame(()=>{chartFrame=null;renderCharts()})}
function renderCards(){
 const i=state.cursor??state.view[1],base=state.view[0];
 const cardsMarkup=state.series.map((s,k)=>{if(state.expandedChart&&state.mode==='split'&&s.symbol!==state.expandedChart)return '';const localView=chartView(state.mode==='split'?s.symbol:'overlay'),index=state.cursor??localView[1],n=state.values[k][index],change=(n/state.values[k][localView[0]]-1)*100;return `<div class="asset-card"><div class="name"><i class="dot" style="background:${coinColor(state.series[k].symbol)}"></i>${escape(assetName(s.symbol))} / USDT</div><div class="numbers"><span class="price">${money(n)}</span><span class="change ${change>=0?'positive':'negative'}">${pct(change)}</span></div>${candleDetails(k,index)}</div>`}).join('');
 if($('asset-cards')._markup!==cardsMarkup){$('asset-cards').innerHTML=cardsMarkup;$('asset-cards')._markup=cardsMarkup}
 $('cursor-label').textContent=(state.pinned?'Fixiert · ':'')+date(state.times[i])+' · Veränderung seit sichtbarem Start';
}
function xFor(i,w,view=state.view){const [a,b]=view,t=state.times;return 14+(t[i]-t[a])/(t[b]-t[a])*(w-87)}
function nearestTime(t){let lo=0,hi=state.times.length-1;while(lo<hi){const mid=Math.floor((lo+hi)/2);if(state.times[mid]<t)lo=mid+1;else hi=mid}return lo>0&&Math.abs(state.times[lo-1]-t)<Math.abs(state.times[lo]-t)?lo-1:lo}
function chartView(key){const stored=state.chartViews[key];if(!stored)return state.view;const view=stored.map(nearestTime);return view[0]<view[1]?view:state.view}
function setChartView(key,view){state.activeChart=key;const keys=state.syncZoom&&state.mode==='split'?state.series.map(s=>s.symbol):[key];for(const k of keys)state.chartViews[k]=view.map(i=>state.times[i])}
function indexAt(event,svg){const r=svg.getBoundingClientRect(),w=r.width,ratio=Math.max(0,Math.min(1,(event.clientX-r.left-14)/(w-87))),[a,b]=svg._chart.view;return Math.max(a,Math.min(b,nearestTime(state.times[a]+ratio*(state.times[b]-state.times[a]))))}
function renderCharts(){
 if(!state.times.length)return;
 $('volume-market').hidden=state.mode==='split';$('volume-note').textContent=state.mode==='split'?'Eigene Volumenskala je Markt':'Volumen des gewählten Markts · eigene Skala';
 const chosen=$('chart-focus').value||'all';$('chart-focus').innerHTML='<option value="all">Alle Coins</option>'+state.series.map(s=>`<option value="${escape(s.symbol)}">${escape(assetName(s.symbol))}</option>`).join('');$('chart-focus').value=state.series.some(s=>s.symbol===chosen)?chosen:'all';
 $('chart-focus').hidden=state.mode!=='overlay';$('candle-key').hidden=state.mode!=='overlay'||$('chart-type').value!=='candles';
 $('coin-legend').innerHTML=state.series.filter(s=>!state.expandedChart||state.mode!=='split'||s.symbol===state.expandedChart).map(s=>`<span style="color:${coinColor(s.symbol)}"><i class="dot" style="background:${coinColor(s.symbol)}"></i>${escape(assetName(s.symbol))}</span>`).join('');
 const area=$('chart-area');area.classList.toggle('pan-mode',state.dragMode==='pan');area.classList.toggle('split',state.mode==='split'&&!state.expandedChart);area.innerHTML='';
 const groups=state.mode==='overlay'?[state.series.map((_,i)=>i)]:state.series.map((_,i)=>[i]).filter(group=>!state.expandedChart||state.series[group[0]].symbol===state.expandedChart);
 for(const group of groups){
 const wrap=document.createElement('div');wrap.className='chart-wrap';area.append(wrap);
 const chartKey=state.mode==='split'?state.series[group[0]].symbol:'overlay',view=chartView(chartKey);
 const w=Math.max(280,wrap.clientWidth),h=state.expandedChart===chartKey?(state.chartHeights[chartKey]||320):320,extra=h-320,[a,b]=view,percent=$('scale').value==='percent';
 const candleMode=$('chart-type').value==='candles';
 const transform=(n,k)=>percent?(n/state.values[k][a]-1)*100:n;
 const vals=group.map(k=>state.values[k].slice(a,b+1).map(n=>percent?(n/state.values[k][a]-1)*100:n));
 let min=Infinity,max=-Infinity;for(const v of vals)for(const n of v){min=Math.min(min,n);max=Math.max(max,n)}
 if(candleMode)for(const k of group)for(let i=a;i<=b;i++){min=Math.min(min,transform(state.candles[k][i].low,k));max=Math.max(max,transform(state.candles[k][i].high,k))}
 const zones=state.scanned?state.hits.filter(z=>group.some(k=>state.series[k].symbol===z.symbol)):[];
 for(const zone of zones){const k=group.find(k=>state.series[k].symbol===zone.symbol);min=Math.min(min,transform(zone.low,k));max=Math.max(max,transform(zone.high,k))}
 const padding=(max-min)*.12||Math.max(Math.abs(max)*.01,1);min-=padding;max+=padding;
 const rangeKey=state.mode+':'+(state.mode==='split'?state.series[group[0]].symbol:'all')+':'+$('scale').value;
 const baseMin=min,baseMax=max,syncSpec=state.syncZoom&&state.mode==='split'?state.syncAxis[$('scale').value]:null;
 if(syncSpec){const span=baseMax-baseMin,center=(baseMax+baseMin)/2+syncSpec.offset*span,half=span*syncSpec.factor/2;min=center-half;max=center+half}
 else if(state.axisRanges[rangeKey]){min=state.axisRanges[rangeKey].min;max=state.axisRanges[rangeKey].max}
 const y=n=>30+(max-n)/(max-min)*(172+extra);
 let content='';for(let j=0;j<5;j++){const yy=30+j*(172+extra)/4,v=max-j*(max-min)/4;content+=`<line x1="14" y1="${yy}" x2="${w-73}" y2="${yy}" stroke="#26303d" stroke-dasharray="3 5"/><text x="${w-63}" y="${yy+4}">${percent?v.toFixed(1)+'%':money(v)}</text>`}
 for(let j=0;j<5;j++){const i=Math.round(a+(b-a)*j/4),x=xFor(i,w,view);content+=`<text x="${x}" y="${307+extra}" text-anchor="${j===0?'start':j===4?'end':'middle'}">${axisDateFormat.format(state.times[i])}</text>`}
 const clipId='price-clip-'+group[0];content+=`<defs><clipPath id="${clipId}"><rect x="12" y="24" width="${w-83}" height="${184+extra}"/></clipPath></defs><g clip-path="url(#${clipId})">`;
 if(!candleMode)group.forEach((k,g)=>{let d='';for(let i=a;i<=b;i++){const gap=i===a||state.times[i]-state.times[i-1]!==steps[state.interval];d+=`${gap?'M':'L'}${xFor(i,w,view).toFixed(2)},${y(vals[g][i-a]).toFixed(2)} `}content+=`<path d="${d}" stroke="${coinColor(state.series[k].symbol)}" stroke-width="1.8" opacity="${state.mode==='overlay'&&$('chart-focus').value!=='all'&&$('chart-focus').value!==state.series[k].symbol?.15:1}" fill="none"/>`});

 if(candleMode){const bw=Math.max(.6,Math.min(10,(w-87)/(b-a+1)*.58));
 const focus=$('chart-focus').value,order=[...group].sort((k,l)=>Number(state.series[k].symbol===focus)-Number(state.series[l].symbol===focus));
 for(const k of order){const overlay=state.mode==='overlay',color=coinColor(state.series[k].symbol),dim=overlay&&focus!=='all'&&state.series[k].symbol!==focus;
 content+=`<g opacity="${dim?.12:1}">`;
 for(let i=a;i<=b;i++){const p=state.candles[k][i],xx=xFor(i,w,view),up=p.close>=p.open,yy=y(transform(Math.max(p.open,p.close),k)),hh=Math.max(1,Math.abs(y(transform(p.open,k))-y(transform(p.close,k)))),stroke=overlay?color:up?'#7fdfb8':'#f48b9c';
 content+=`<line x1="${xx}" x2="${xx}" y1="${y(transform(p.high,k))}" y2="${y(transform(p.low,k))}" stroke="${stroke}"/><rect x="${xx-bw/2}" y="${yy}" width="${bw}" height="${hh}" fill="${overlay&&up?'none':stroke}" fill-opacity="${overlay?.65:1}" stroke="${stroke}" stroke-width="1"/>`}
 content+='</g>';
 }}
 for(const zone of zones){const k=group.find(k=>state.series[k].symbol===zone.symbol),top=y(transform(zone.high,k)),bottom=y(transform(zone.low,k));content+=`<rect x="14" y="${top-1}" width="${w-87}" height="${Math.max(2,bottom-top)}" fill="${coinColor(zone.symbol)}" fill-opacity=".18" stroke="${coinColor(zone.symbol)}" stroke-dasharray="5 4"/><text x="20" y="${Math.max(36,top-5)}" style="fill:${coinColor(zone.symbol)}">${escape(assetName(zone.symbol))} R${zone.rank} ${money(zone.low)} – ${money(zone.high)} USDT</text>`}
 content+='</g>'+`<g transform="translate(0,${extra})">${volumeBars(group,w,a,b)}</g>`;
 content+=`<rect class="price-axis-hit" x="${w-72}" y="20" width="72" height="${192+extra}" fill="transparent" style="cursor:ns-resize"><title>Achse ziehen: vertikal skalieren. Doppelklick: automatisch skalieren.</title></rect>`;
 content+=`<g class="measurement-overlay" pointer-events="none"></g><g class="cursor" pointer-events="none"></g><rect class="selection" y="20" height="${260+extra}" fill="#d7f58a18" stroke="#d7f58a66" visibility="hidden"/>`;
 wrap.innerHTML=(state.mode==='split'?`<span class="chart-name">${escape(state.series[group[0]].symbol)}</span>`:'')+`<svg style="height:${h}px" viewBox="0 0 ${w} ${h}" role="img" aria-label="Interaktiver Kursvergleich" tabindex="0">${content}</svg>`;
 const zoomControls=document.createElement('div');zoomControls.className='chart-zoom-controls';zoomControls.innerHTML='<button type="button" class="zoom-out" aria-label="Chart verkleinern" title="Herauszoomen">−</button><button type="button" class="zoom-in" aria-label="Chart vergrößern" title="Hineinzoomen">+</button>';wrap.append(zoomControls);
 zoomControls.querySelector('.zoom-in').onclick=()=>zoomTime(.7,svg._chart);zoomControls.querySelector('.zoom-out').onclick=()=>zoomTime(1/.7,svg._chart);

 const singleFullscreen=document.createElement('button');singleFullscreen.className='single-fullscreen';singleFullscreen.type='button';singleFullscreen.textContent=state.expandedChart===chartKey?'⛶ Zurück':'⛶';singleFullscreen.title=state.expandedChart===chartKey?'Alle Charts wieder anzeigen':'Diesen Chart im Vollbild anzeigen';singleFullscreen.setAttribute('aria-label',singleFullscreen.title);singleFullscreen.setAttribute('aria-pressed',String(state.expandedChart===chartKey));singleFullscreen.onclick=()=>toggleSingleChart(chartKey);wrap.append(singleFullscreen);
 if(state.expandedChart===chartKey){
 const handle=document.createElement('div');handle.className='chart-height-handle';handle.setAttribute('role','separator');handle.setAttribute('aria-orientation','horizontal');handle.setAttribute('aria-label','Charthöhe durch Ziehen ändern');handle.setAttribute('aria-valuenow',String(h));handle.setAttribute('aria-valuemin','320');handle.setAttribute('aria-valuemax','1600');handle.tabIndex=0;handle.title='Nach unten ziehen: Chart vergrößern · Doppelklick: Standardhöhe';handle.innerHTML='<span></span>';wrap.append(handle);
 handle.onpointerdown=e=>{if(e.button!==0)return;e.preventDefault();e.stopPropagation();const start=e.clientY,pointer=e.pointerId;state.resizingChart=true;area.setPointerCapture(pointer);
 const move=event=>{if(event.pointerId!==pointer)return;event.preventDefault();state.chartHeights[chartKey]=Math.max(320,Math.min(1600,h+event.clientY-start));scheduleChartRender()};
 const finish=event=>{if(event.pointerId!==pointer)return;state.resizingChart=false;area.removeEventListener('pointermove',move);area.removeEventListener('pointerup',finish);area.removeEventListener('pointercancel',finish);if(area.hasPointerCapture(pointer))area.releasePointerCapture(pointer)};
 area.addEventListener('pointermove',move);area.addEventListener('pointerup',finish);area.addEventListener('pointercancel',finish);
 };
 handle.ondblclick=()=>{delete state.chartHeights[chartKey];renderCharts()};
 handle.onkeydown=e=>{if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();state.chartHeights[chartKey]=Math.max(320,Math.min(1600,h+(e.key==='ArrowDown'?40:-40)));renderCharts();$('chart-area').querySelector('.chart-height-handle')?.focus()}};
 }
 const svg=wrap.querySelector('svg');
 const axis=svg.querySelector('.price-axis-hit');
 axis.onpointerdown=e=>{if(e.button!==0)return;e.preventDefault();e.stopPropagation();state.axisDragging=true;window.getSelection()?.removeAllRanges();const origin=e.clientY,initial={min,max};area.setPointerCapture(e.pointerId);
 const move=event=>{if(event.pointerId!==e.pointerId)return;event.preventDefault();state.activeChart=chartKey;setAxisRange({rangeKey,baseMin,baseMax},axisRange(initial,event.clientY-origin));scheduleChartRender()};
 const finish=event=>{if(event.pointerId!==e.pointerId)return;state.axisDragging=false;area.removeEventListener('pointermove',move);area.removeEventListener('pointerup',finish);area.removeEventListener('pointercancel',finish);if(area.hasPointerCapture(e.pointerId))area.releasePointerCapture(e.pointerId)};
 area.addEventListener('pointermove',move);area.addEventListener('pointerup',finish);area.addEventListener('pointercancel',finish);
 };
 axis.ondblclick=e=>{e.preventDefault();e.stopPropagation();if(state.syncZoom&&state.mode==='split'){delete state.syncAxis[$('scale').value];for(const k of Object.keys(state.axisRanges))if(k.endsWith(':'+ $('scale').value))delete state.axisRanges[k]}else delete state.axisRanges[rangeKey];renderCharts()};
 svg._chart={group,w,y,percent,min,max,baseMin,baseMax,rangeKey,view,chartKey,extra};let drag=null;
 let middleZoom=false,wheelDelta=0,wheelFrame=null;
 const flushWheelZoom=()=>{wheelFrame=null;const delta=wheelDelta;wheelDelta=0;if(!delta)return;
 const current=[...area.querySelectorAll('svg')].map(el=>el._chart).find(c=>c?.chartKey===chartKey);if(current)zoomTime(Math.exp(Math.max(-.7,Math.min(.7,delta*.002))),current);
 };
 svg.addEventListener('wheel',e=>{if(!(state.middleZoomKey===chartKey||(e.buttons&4)))return;e.preventDefault();e.stopPropagation();wheelDelta+=e.deltaY*(e.deltaMode===1?16:e.deltaMode===2?svg.clientHeight:1);if(wheelFrame===null)wheelFrame=requestAnimationFrame(flushWheelZoom)},{passive:false});
 svg.onauxclick=e=>{if(e.button===1)e.preventDefault()};
 svg.addEventListener('pointerdown',e=>{if(e.button!==1)return;e.preventDefault();e.stopImmediatePropagation();middleZoom=true;state.middleZoomKey=chartKey;area.classList.add('click-zooming');
 const finish=event=>{if(event.button!==1&&event.type!=='blur'&&event.type!=='pointercancel')return;middleZoom=false;state.middleZoomKey=null;area.classList.remove('click-zooming');window.removeEventListener('pointerup',finish);window.removeEventListener('pointercancel',finish);window.removeEventListener('blur',finish)};
 window.addEventListener('pointerup',finish);window.addEventListener('pointercancel',finish);window.addEventListener('blur',finish);
 },true);
 svg.onselectstart=e=>e.preventDefault();
 svg.ondragstart=e=>e.preventDefault();
 svg.onpointerdown=e=>{if(e.button!==0)return;e.preventDefault();window.getSelection()?.removeAllRanges();svg.focus({preventScroll:true});if(state.dragMode==='pan'){startPan(e,svg,area);return}drag=indexAt(e,svg);svg.setPointerCapture(e.pointerId);if(state.dragMode==='measure'){state.measurement={start:state.times[drag],end:state.times[drag]};renderMeasurement()}};
 svg.onpointermove=e=>{if(drag!==null)e.preventDefault();const i=indexAt(e,svg);if(drag!==null&&state.dragMode==='measure'&&state.measurement?.end!==state.times[i]){state.measurement={start:state.times[drag],end:state.times[i]};scheduleMeasurementRender()}if(drag!==null&&state.dragMode==='zoom'){const x1=xFor(drag,w,view),x2=xFor(i,w,view),rect=svg.querySelector('.selection');rect.setAttribute('x',Math.min(x1,x2));rect.setAttribute('width',Math.abs(x2-x1));rect.setAttribute('visibility','visible')}if(!state.pinned&&state.cursor!==i){state.cursor=i;scheduleCursorRender()}};
 svg.onpointerup=e=>{if(drag===null)return;const i=indexAt(e,svg);if(state.dragMode==='measure'&&i!==drag){state.measurement={start:state.times[drag],end:state.times[i]};state.cursor=i;state.pinned=true;renderMeasurement();updateCursor();renderCards()}else if(state.dragMode==='zoom'&&Math.abs(i-drag)>=3){setChartView(chartKey,[Math.min(i,drag),Math.max(i,drag)]);state.cursor=null;state.pinned=false;renderCharts();renderCards()}else{state.cursor=i;state.pinned=true;$('pin-date').value=localInput(state.times[i]);updateCursor();renderCards()}drag=null;svg.querySelector('.selection')?.setAttribute('visibility','hidden')};
 svg.onpointercancel=()=>{if(state.dragMode==='measure'){state.measurement=null;renderMeasurement()}drag=null;svg.querySelector('.selection').setAttribute('visibility','hidden')};
 svg.onpointerleave=()=>{if(!state.pinned&&drag===null&&state.cursor!==null){state.cursor=null;scheduleCursorRender()}};
 svg.ondblclick=()=>{if(state.dragMode!=='measure')resetZoom(chartKey)};
 svg.onkeydown=e=>{if(['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();state.cursor=Math.max(a,Math.min(b,(state.cursor??a)+(e.key==='ArrowRight'?1:-1)));state.pinned=true;updateCursor();renderCards()}};
 }
 updateCursor();renderMeasurement();
}
function updateCursor(){document.querySelectorAll('svg').forEach(svg=>{const c=svg._chart;if(!c)return;const group=svg.querySelector('.cursor'),i=state.cursor;if(i===null||i<c.view[0]||i>c.view[1]){group.innerHTML='';return}const x=xFor(i,c.w,c.view);group.innerHTML=`<line x1="${x}" y1="24" x2="${x}" y2="${280+c.extra}" stroke="#9eabbc" stroke-dasharray="4 4"/>`+c.group.map(k=>{const n=state.values[k][i],v=c.percent?(n/state.values[k][c.view[0]]-1)*100:n;return `<circle cx="${x}" cy="${c.y(v)}" r="4" fill="${coinColor(state.series[k].symbol)}" stroke="#121923" stroke-width="2"/>`}).join('')})}
function resetZoom(key){if(!state.times.length)return;if(typeof key==='string'&&!state.syncZoom){delete state.chartViews[key];for(const rangeKey of Object.keys(state.axisRanges))if(rangeKey.startsWith(key==='overlay'?'overlay:':'split:'+key+':'))delete state.axisRanges[rangeKey]}else{state.view=[0,state.times.length-1];state.chartViews={};state.axisRanges={};state.syncAxis={};}state.cursor=null;state.pinned=false;renderCharts();renderCards()}
function runScan(fit=true){
 if(!state.series.length){notice('Bitte zuerst mindestens einen Markt laden.');return}
 state.hits=state.series.flatMap((s,k)=>strongestResistances(s.points,steps[state.interval]).map(z=>({...z,k,symbol:s.symbol})));state.scanned=true;$('chart-resistances').textContent='Widerstände ausblenden';$('chart-resistances').setAttribute('aria-pressed','true');
 $('scan-summary').innerHTML=`<span><strong>${state.hits.length}</strong> wichtigste Widerstandszonen · direkt in den Charts markiert</span><span>${state.series.length} Märkte · geladener Zeitraum · ${state.interval}</span>`;
 if(fit){state.axisRanges={};state.syncAxis={};}renderCharts();
 $('pair-summary').innerHTML='';
 if(!state.hits.length){$('scan-results').innerHTML='<p>Keine bestätigten Widerstandszonen gefunden. Im geladenen Zeitraum liegen nicht genügend wiederholte, bestätigte Hochs über dem aktuellen Kurs vor.</p>';return}
 $('scan-results').innerHTML=`<table><thead><tr><th>Coin</th><th>Gewichtung</th><th>Zone (USDT)</th><th>Abstand</th><th>Berührungen</th><th>Zuletzt bestätigt (UTC)</th><th>Status</th><th></th></tr></thead><tbody>${state.hits.map((z,i)=>`<tr><td><span style="color:${coinColor(z.symbol)}">${escape(assetName(z.symbol))}</span></td><td>R${z.rank} · ${z.score.toFixed(1)}</td><td>${money(z.low)} – ${money(z.high)}</td><td>${z.distance.toFixed(2)} %</td><td>${z.touches}</td><td>${date(z.last)}</td><td>${z.inside?'Kurs in Zone':'Über letztem Kurs'}</td><td><button class="subtle resistance-open" data-zone="${i}">Im Chart ↗</button></td></tr>`).join('')}</tbody></table>`;
 $('scan-results').querySelectorAll('.resistance-open').forEach(button=>button.onclick=()=>{
 const zone=state.hits[Number(button.dataset.zone)];
 for(const key of Object.keys(state.axisRanges))if(key.includes(':'+zone.symbol+':')||key.startsWith('overlay:'))delete state.axisRanges[key];state.syncAxis={};
 if(state.mode==='overlay')$('chart-focus').value=zone.symbol;
 renderCharts();$('chart-area').scrollIntoView({behavior:'smooth',block:'center'});
 });
}
function pannedRange(view,total,deltaX,width){const span=view[1]-view[0],shift=Math.round(-deltaX/Math.max(1,width)*span),first=Math.max(0,Math.min(total-1-span,view[0]+shift));return [first,first+span]}
function startPan(e,svg,area){
 const c=svg._chart,origin=e.clientX,rect=svg.getBoundingClientRect(),initial=[...c.view],pointer=e.pointerId;let moved=false,last=initial;
 state.panDragging=true;area.classList.add('panning');area.setPointerCapture(pointer);
 const move=event=>{if(event.pointerId!==pointer)return;event.preventDefault();if(Math.abs(event.clientX-origin)<3&&!moved)return;moved=true;
 const view=pannedRange(initial,state.times.length,event.clientX-origin,rect.width-87);if(view[0]===last[0]&&view[1]===last[1])return;last=view;setChartView(c.chartKey,view);scheduleChartRender();
 };
 const finish=event=>{if(event.pointerId!==pointer)return;state.panDragging=false;area.classList.remove('panning');area.removeEventListener('pointermove',move);area.removeEventListener('pointerup',finish);area.removeEventListener('pointercancel',finish);if(area.hasPointerCapture(pointer))area.releasePointerCapture(pointer);
 if(!moved&&event.type==='pointerup'){state.cursor=indexAt(event,svg);state.pinned=true;updateCursor();renderCards()}else renderCards();
 };
 area.addEventListener('pointermove',move);area.addEventListener('pointerup',finish);area.addEventListener('pointercancel',finish);
}
function zoomedRange(view,total,factor){const width=Math.min(total-1,Math.max(2,Math.round((view[1]-view[0])*factor))),center=(view[0]+view[1])/2;let first=Math.max(0,Math.round(center-width/2));first=Math.min(first,total-1-width);return [first,first+width]}
function setAxisRange(c,range){
 if(state.syncZoom&&state.mode==='split'){const span=c.baseMax-c.baseMin;state.syncAxis[$('scale').value]={factor:(range.max-range.min)/span,offset:((range.max+range.min)/2-(c.baseMax+c.baseMin)/2)/span}}
 else state.axisRanges[c.rangeKey]=range;
}
function zoomTime(factor,c){if(!state.times.length||!c)return;const center=(c.min+c.max)/2,half=(c.max-c.min)/2*factor;if(Number.isFinite(half)&&half>1e-12)setAxisRange(c,{min:center-half,max:center+half});setChartView(c.chartKey,zoomedRange(c.view,state.times.length,factor));renderCharts();renderCards()}
function axisRange(initial,deltaY){const center=(initial.min+initial.max)/2,half=(initial.max-initial.min)/2*Math.exp(Math.max(-6,Math.min(6,deltaY/120)));return {min:center-half,max:center+half}}
function measurementChanges(values,first,last){
 const a=Math.min(first,last),b=Math.max(first,last);
 return values.map(v=>({start:v[a],end:v[b],change:(v[b]/v[a]-1)*100}));
}
let measurementFrame=null;
function scheduleMeasurementRender(){if(measurementFrame!==null)return;measurementFrame=requestAnimationFrame(()=>{measurementFrame=null;renderMeasurement()})}
function renderMeasurement(){
 const box=$('measurement');
 document.querySelectorAll('.measurement-overlay').forEach(g=>g.innerHTML='');
 if(!state.measurement||!state.times.length){box.hidden=true;return}
 const start=Math.min(state.measurement.start,state.measurement.end),end=Math.max(state.measurement.start,state.measurement.end);
 if(start<state.times[0]||end>state.times.at(-1)){state.measurement=null;box.hidden=true;return}
 const first=nearestTime(start),last=nearestTime(end),changes=measurementChanges(state.values,first,last);
 const provisional=state.candles.some(c=>c[first].closed===false||c[last].closed===false);
 box.hidden=false;
 box.innerHTML=`<div class="measurement-heading"><span><strong>Messung · Schlusskurs → Schlusskurs</strong><br>${date(start)} → ${date(end)}${provisional?' · laufende Kerze, vorläufig':''}</span><button id="clear-measurement" class="subtle">Messung löschen ×</button></div><div class="measurement-values">${changes.map((m,k)=>`<div><span>${escape(assetName(state.series[k].symbol))}</span><strong class="${m.change>=0?'positive':'negative'}">${pct(m.change)}</strong><small>${money(m.start)} → ${money(m.end)} USDT</small></div>`).join('')}</div>`;
 $('clear-measurement').onclick=()=>{state.measurement=null;renderMeasurement()};
 document.querySelectorAll('svg').forEach(svg=>{const c=svg._chart;if(!c)return;const [a,b]=c.view;if(last<a||first>b)return;
 const x1=xFor(Math.max(a,first),c.w,c.view),x2=xFor(Math.min(b,last),c.w,c.view),g=svg.querySelector('.measurement-overlay');
 const k=c.group[0],positive=changes[k].change>=0,color=positive?'#7fdfb8':'#f48b9c';
 const value=i=>c.percent?(state.values[k][i]/state.values[k][a]-1)*100:state.values[k][i];
 g.innerHTML=`<rect x="${x1}" y="24" width="${Math.max(1,x2-x1)}" height="${184+c.extra}" fill="${color}" fill-opacity=".1" stroke="${color}" stroke-dasharray="4 3"/>`;
 if(first>=a&&last<=b){g.innerHTML+=`<line x1="${x1}" y1="${c.y(value(first))}" x2="${x2}" y2="${c.y(value(last))}" stroke="${color}" stroke-width="2"/><circle cx="${x1}" cy="${c.y(value(first))}" r="3" fill="${color}"/><circle cx="${x2}" cy="${c.y(value(last))}" r="3" fill="${color}"/>`}
 if(c.group.length===1){const xx=Math.max(16,Math.min(c.w-158,(x1+x2)/2-38));g.innerHTML+=`<rect x="${xx}" y="28" width="95" height="24" rx="4" fill="#101721" stroke="${color}"/><text x="${xx+48}" y="44" text-anchor="middle" style="fill:${color};font-size:12px">${pct(changes[k].change)}</text>`}
 });
}
for(const mode of ['pan','zoom','measure'])$('drag-'+mode).onclick=()=>{
 state.dragMode=mode;
 for(const m of ['pan','zoom','measure']){$('drag-'+m).classList.toggle('active',mode===m);$('drag-'+m).setAttribute('aria-pressed',String(mode===m))}
 $('drag-hint').textContent=mode==='pan'?'Ziehen zum Verschieben · zum Navigieren zunächst hineinzoomen':mode==='measure'?'Ziehen zum Messen · Schlusskurs am Anfang und Ende · Zeitspanne chronologisch':'Ziehen zum Zoomen · Doppelklick zum Zurücksetzen';
 if(mode==='zoom')state.measurement=null;
 if(state.times.length)renderCharts();else renderMeasurement();
};
async function toggleSingleChart(key){
 const panel=$('chart-workspace'),active=document.fullscreenElement===panel||document.webkitFullscreenElement===panel;
 if(state.expandedChart===key){state.expandedChart=null;renderCharts();renderCards();if(active&&!state.expandedFromFullscreen){try{if(document.exitFullscreen)await document.exitFullscreen();else document.webkitExitFullscreen()}catch{}}return}
 state.expandedChart=key;state.expandedFromFullscreen=active;renderCharts();renderCards();
 if(!active){try{if(panel.requestFullscreen)await panel.requestFullscreen();else if(panel.webkitRequestFullscreen)panel.webkitRequestFullscreen()}catch{notice('Der Chart ist einzeln vergrößert. Der Browser hat den Bildschirm-Vollbildmodus nicht freigegeben.')}}
}
function syncFullscreenButton(){
 const active=document.fullscreenElement===$('chart-workspace')||document.webkitFullscreenElement===$('chart-workspace');
 $('fullscreen').textContent=active?'⛶ Vollbild beenden':'⛶ Vollbild';$('fullscreen').setAttribute('aria-pressed',String(active));
 if(!active)state.expandedChart=null;
 scheduleChartRender();if(state.times.length)renderCards();
}
$('chart-resistances').onclick=()=>{if(state.scanned){resetScan();renderCharts()}else runScan()};
$('fullscreen').onclick=async()=>{
 const panel=$('chart-workspace');
 try{if(document.fullscreenElement||document.webkitFullscreenElement){if(document.exitFullscreen)await document.exitFullscreen();else document.webkitExitFullscreen()}
 else if(panel.requestFullscreen)await panel.requestFullscreen();else if(panel.webkitRequestFullscreen)panel.webkitRequestFullscreen();else notice('Dieser Browser unterstützt den Vollbildmodus nicht.');}
 catch{notice('Vollbild konnte nicht geöffnet werden. Bitte den Button erneut im normalen Browser anklicken.');}
};
document.addEventListener('fullscreenchange',syncFullscreenButton);
document.addEventListener('webkitfullscreenchange',syncFullscreenButton);
$('sync-zoom').onclick=()=>{
 const charts=[...document.querySelectorAll('svg')].map(svg=>svg._chart).filter(Boolean),source=charts.find(c=>c.chartKey===state.activeChart)||charts[0];
 if(state.syncZoom){for(const c of charts)state.axisRanges[c.rangeKey]={min:c.min,max:c.max};state.syncZoom=false}
 else{state.syncZoom=true;if(source&&state.mode==='split'){setChartView(source.chartKey,source.view);setAxisRange(source,{min:source.min,max:source.max})}}
 $('sync-zoom').textContent=state.syncZoom?'Zoom synchron':'Zoom separat';$('sync-zoom').classList.toggle('active',state.syncZoom);$('sync-zoom').setAttribute('aria-pressed',String(state.syncZoom));renderCharts();
};
$('live').onclick=connect;$('load').onclick=()=>load();$('scan').onclick=()=>runScan();
$('market-search').oninput=search;$('market-search').onfocus=search;$('browse').onclick=search;
$('market-search').onkeydown=e=>{if(e.key==='Escape')$('search-results').hidden=true;if(e.key==='ArrowDown'){$('search-results').querySelector('button')?.focus();e.preventDefault()}};
$('search-results').onkeydown=e=>{if(e.key==='Escape'){$('search-results').hidden=true;$('market-search').focus()}};
 document.addEventListener('click',e=>{if(!e.target.closest('.market-picker'))$('search-results').hidden=true});
 for(const mode of ['overlay','split'])$(mode).onclick=()=>{state.expandedChart=null;state.mode=mode;if(mode==='overlay'&&$('chart-type').value==='candles')$('scale').value='percent';$('overlay').classList.toggle('active',mode==='overlay');$('split').classList.toggle('active',mode==='split');renderCharts()};
 $('chart-type').onchange=()=>{if($('chart-type').value==='candles'&&state.mode==='overlay')$('scale').value='percent';renderCharts()};
 $('chart-focus').onchange=renderCharts;
 $('volume-unit').onchange=renderCharts;$('volume-market').onchange=renderCharts;
 $('scale').onchange=()=>{renderCharts();if(state.times.length)renderCards()};$('reset-zoom').onclick=resetZoom;
 $('pin').onclick=()=>{if(!state.times.length)return;const t=Date.parse($('pin-date').value+'Z');if(!Number.isFinite(t)||t<state.times[0]||t>state.times.at(-1)){notice('Bitte einen Zeitpunkt innerhalb der geladenen Daten wählen.');return}const i=nearestTime(t);state.cursor=i;state.pinned=true;if(i<state.view[0]||i>state.view[1])state.view=[0,state.times.length-1];renderCharts();renderCards()};
 $('unpin').onclick=()=>{state.cursor=null;state.pinned=false;if(state.times.length){updateCursor();renderCards()}};
 document.querySelectorAll('[data-days]').forEach(b=>b.onclick=()=>{setDates(Number(b.dataset.days));dirty()});
 ['start','end','interval'].forEach(id=>$(id).onchange=dirty);
 $('hide-resistances').onclick=()=>{resetScan();renderCharts()};
 let resize;window.addEventListener('resize',()=>{clearTimeout(resize);resize=setTimeout(renderCharts,100)});
 $('end').disabled=$('auto-live').checked;setDates(7);renderSelected();connect();

$('auto-live').onchange=()=>{$('end').disabled=$('auto-live').checked;dirty()};
$('scan-all').onclick=async()=>{if(state.busy)return;state.dirty=true;state.selected=SYMBOLS.filter(s=>state.markets.some(m=>m.symbol===s));renderSelected();await load();if(!state.dirty&&state.series.length)runScan()};
$('export').onclick=()=>{if(!state.hits.length){notice('Zuerst Widerstandszonen berechnen.');return}const rows=[['Coin','Zone unten USDT','Zone oben USDT','Abstand %','Beruehrungen','Erstes Hoch UTC','Letztes Hoch UTC'],...state.hits.map(z=>[z.symbol,z.low,z.high,z.distance,z.touches,new Date(z.first).toISOString(),new Date(z.last).toISOString()])];const url=URL.createObjectURL(new Blob(['\ufeff'+rows.map(r=>r.join(';')).join('\n')],{type:'text/csv;charset=utf-8'})),link=document.createElement('a');link.href=url;link.download='stockscreen-widerstaende.csv';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
setInterval(()=>{if($('auto-live').checked&&state.lastSuccess&&Date.now()-state.lastSuccess>45000){$('data-badge').textContent='VERALTET';$('connection').textContent='○ Live-Aktualisierung ausstehend'}if(!document.hidden&&$('auto-live').checked&&!state.dirty&&!state.busy&&!state.axisDragging&&!state.panDragging&&!state.resizingChart&&state.series.length)load(true)},15000);

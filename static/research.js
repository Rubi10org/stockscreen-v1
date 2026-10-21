const $=id=>document.getElementById(id);
const esc=value=>String(value??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=value=>Number.isFinite(value)?value.toLocaleString('de-DE',{maximumFractionDigits:3}):'—';
function table(headers,rows){return '<table><thead><tr>'+headers.map(v=>'<th>'+esc(v)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(row=>'<tr>'+row.map(v=>'<td>'+esc(v)+'</td>').join('')+'</tr>').join('')+'</tbody></table>'}
export function renderResearch(data){
 const names={running:'Läuft',done:'Abgeschlossen',partial:'Teilweise abgeschlossen',paused:'Pausiert',error:'Fehler'};
 const active=data.suite?.status==='running'?data.studies.find(s=>s.status==='running'&&s.profile===data.suite.profile):null;
 $('research-progress-wrap').hidden=!active;
 if(active){
  const partial=Math.min(100,Math.max(0,active.progress?.percent||0))/100;
  const percent=active.plannedWindows>0?Math.min(99.9,(active.completedWindows+partial)/active.plannedWindows*100):null;
  if(percent!==null)$('research-progress').value=percent;else $('research-progress').removeAttribute('value');
  $('research-progress-percent').textContent=percent!==null?num(Math.round(percent*10)/10)+' %':'Wird vorbereitet …';
  $('research-progress-text').textContent=active.venue+' · '+active.symbol.replace('USDT','')+'/'+active.quote+' · '+active.completedWindows+' von '+(active.plannedWindows||'—')+' Fenstern gespeichert · '+active.stage+(active.progress?' · aktuelles Fenster: '+active.progress.percent+' % · '+num(active.progress.elapsedSeconds)+' s':'');
  $('research-progress-updated').textContent='Status abgerufen um '+new Date().toLocaleTimeString('de-DE')+' · aktualisiert sich alle 5 Sekunden';
 }
 $('research-state').textContent=data.suite?(names[data.suite.status]||data.suite.status)+' · '+data.suite.profile+' · '+(data.suite.errors?.length||0)+' gemeldete Daten-/Studienprobleme':'Noch kein Vergleichslauf gestartet.';
 $('research-data').innerHTML=table(['Quelle / Markt','Kerzen','Abdeckung','Längste Folge'],data.datasets.map(d=>[d.venue+' · '+d.symbol.replace('USDT','')+'/'+d.quote,num(d.candles)+' / '+num(d.expected),num(d.coveragePct)+' %',num(d.longestContiguous)+' h']));
 $('research-studies').innerHTML=data.studies.length?table(['Studie','Status / Fortschritt','Auswahl','Testfenster','Modellfehler / Referenz','Test-Abdeckung 1/4/12/24 h'],data.studies.map(s=>[
  s.venue+' · '+s.symbol.replace('USDT','')+'/'+s.quote+' · '+s.profile+(s.inputCandles?' · '+num(s.inputCandles)+' Eingangskerzen':''),
  (names[s.status]||s.status)+' · '+s.completedWindows+' / '+s.plannedWindows+' Fenster · '+(s.error||s.stage||''),
  s.selected?.id||'Auswahl läuft',s.test?.windows||'—',
  s.test?num(s.test.modelMAPE)+' % / '+num(s.test.baselineMAPE)+' %':'Noch keine endgültigen Testwerte',
  s.calibratedTest?.available?['1','4','12','24'].map(h=>num(s.calibratedTest.horizons[h].coveragePct)+' %').join(' / '):'Noch keine ausreichende Kalibrierung'
 ])):'<p>Noch keine Studien gespeichert.</p>';
 const j=data.journal;
 $('research-journal').textContent=j.forecasts+' Prognosen gespeichert · '+j.completedForecasts+' vollständig ausgewertet · '+j.scoredTargets+' bewertete Zielkurse. '+(j.scoredTargets?'Mittlerer absoluter Prozentfehler: '+num(j.mapePct)+' %; Referenz „letzter Kurs bleibt gleich“: '+num(j.baselineMAPEPct)+' %. 10–90%-Szenarioabdeckung: '+num(j.scenarioCoveragePct)+' %. ':'')+j.note;
}
let loading=false;
async function refresh(){
 if(loading||document.hidden)return;loading=true;
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
 try{const response=await fetch('/api/research/status',{cache:'no-store',signal:controller.signal});const data=await response.json();if(!response.ok)throw Error(data.error||'Status nicht verfügbar');renderResearch(data)}
 catch(error){$('research-state').textContent='Forschungsstatus nicht verfügbar · '+error.message+' · nach einem Update den Datenserver neu starten.';$('research-progress-updated').textContent='Statusabruf fehlgeschlagen. Angezeigter Fortschritt kann veraltet sein.'}
 finally{loading=false;clearTimeout(timer)}
}
$('research-refresh').onclick=refresh;
setInterval(refresh,5000);refresh();

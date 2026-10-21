// Explicit planning heuristics, separate from Kronos inference. No orders.
const HOUR=3600000;
const positive=n=>Number.isFinite(n)&&n>0;
export function analyzeForecast(result,quote={},now=Date.now()){
 const out={summary:'Keine auswertbare Prognose.',reasons:[],warnings:[],plan:null};
 const history=result?.history,points=result?.points;
 if(result?.quote!=='EUR'||!history?.length||points?.length!==24)return out;
 const base=history.at(-1).close,last=points.at(-1);
 if(![base,last.close,last.median,last.p10,last.p90].every(positive)||last.p10>last.median||last.median>last.p90)return out;
 const change=(last.median/base-1)*100,direction=change>0?1:change<0?-1:0;
 Object.assign(out,{base,change,direction,band:[last.p10,last.p90],targetTime:last.time});
 out.summary='Der Median nach 24 Stunden liegt '+(change>=0?'über':'unter')+' dem letzten Kerzenschluss. Die Szenariospanne beschreibt Modellstreuung, keine Eintrittswahrscheinlichkeit.';
 if(!Number.isFinite(result.generatedAt)||result.generatedAt>now||now-result.generatedAt>HOUR)out.reasons.push('Prognose veraltet oder ohne gültigen Berechnungszeitpunkt – neu berechnen.');
 if(!Number.isFinite(result.dataAsOf)||result.dataAsOf>now||now-result.dataAsOf>HOUR+120000)out.reasons.push('Die zugrunde liegenden Marktkerzen sind nicht aktuell.');
 if(points.some((p,i)=>p.time!==result.dataAsOf+(i+1)*HOUR||![p.close,p.median,p.p10,p.p90].every(positive)))out.reasons.push('Prognosezeitachse oder Zielkurse sind ungültig.');
 if(history.length<128)out.reasons.push('Für diese Planungsregel werden mindestens 128 echte Eingangskerzen verlangt.');
 if(!positive(quote.price)||!Number.isFinite(quote.retrievedAt)||quote.retrievedAt>now||now-quote.retrievedAt>60000)out.reasons.push('Kein aktueller Bitvavo-Livekurs für die Einstiegsprüfung (höchstens 60 Sekunden alt).');
 if(!direction||direction*(last.close-base)<=0)out.reasons.push('Mittelwert und Median liefern keine gemeinsame Modellrichtung.');
 if(result.dataQuality?.sparseHistory)out.warnings.push('Eingabe enthält Zeitlücken; Prognosequalität dafür nicht nachgewiesen.');
 const recent=history.slice(-15);
 if(recent.length!==15||recent.some((p,i)=>![p.high,p.low,p.close].every(positive)||p.high<p.low||i&&p.time-recent[i-1].time!==HOUR))out.reasons.push('Die letzten 15 Kerzen müssen für die Stop-Berechnung gültig und lückenlos sein.');
 if(out.reasons.length)return out;
 const atr=recent.slice(1).reduce((s,p,i)=>s+Math.max(p.high-p.low,Math.abs(p.high-recent[i].close),Math.abs(p.low-recent[i].close)),0)/14;
 if(!(atr>0)){out.reasons.push('Keine verwertbare Schwankungsbreite für einen Stop.');return out;}
 // Fixed to this forecast's closing price; the entry zone never chases the ticker.
 const zone=[base-.2*atr,base+.2*atr],entry=direction>0?zone[1]:zone[0];
 const stop=base-direction*1.5*atr,target2=last.median;
 if(![zone[0],stop].every(positive)||direction*(target2-entry)<=0){out.reasons.push('Modellziel liegt nicht jenseits einer sinnvollen Entry-Zone.');return out;}
 const midpoint=entry+(target2-entry)/2,median12=points[11].median;
 const target1=direction*(median12-entry)>0&&direction*(target2-median12)>0?median12:midpoint;
 const tradingRate=.0025,slippageRate=.001,borrowingHourly=.000023;
 const costs=exit=>(entry+exit)*(tradingRate+slippageRate)+Math.max(entry,stop,target2)*borrowingHourly*24;
 const unitRisk=Math.abs(entry-stop)+costs(stop);
 const profit1=direction*(target1-entry)-costs(target1),profit2=direction*(target2-entry)-costs(target2);
 const rr=(profit1+profit2)/2/unitRisk;
 out.plan={side:direction>0?'Long':'Short',zone,entry,stop,target1,target2,atr,rr,unitRisk,riskPct:unitRisk/entry*100,
  validUntil:Math.min(result.generatedAt+HOUR,result.dataAsOf+HOUR+120000),timeExit:last.time,
  profit1,profit2,tradingRate,slippageRate,borrowingHourly};
 if(!result.validation?.available)out.reasons.push('Kein auswertbarer historischer Vergleich für diese Prognose.');
 else if(result.validation.beatsBaselineMAE!==true)out.reasons.push('Kronos schlug im letzten Vergleichsfenster die Referenz „letzter Kurs bleibt gleich“ nicht.');
 if(profit1<=0||rr<2)out.reasons.push('Die geplanten Teilverkäufe erreichen nach den Kostenannahmen kein Chance-Risiko-Verhältnis von mindestens 2:1.');
 if(quote.price<zone[0]||quote.price>zone[1])out.reasons.push('Livekurs außerhalb der festen Entry-Zone; dem Kurs nicht hinterherlaufen.');
 if(direction*(quote.price-stop)<=0||direction*(target2-quote.price)<=0)out.reasons.push('Stop oder Endziel ist bereits erreicht; neue Prognose erforderlich.');
 out.warnings.push('Regelbasiertes Modellszenario; diese Entry-/Exit-Regeln sind nicht als Handelsstrategie validiert.');
 return out;
}

const f=n=>Number.isFinite(n)?new Intl.NumberFormat('de-DE',{maximumFractionDigits:6}).format(n):'—';
const eur=n=>f(n)+' €';
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function renderForecastPosition(result,quote={},now=Date.now()){
 const section=document.getElementById('forecast-position');
 section.hidden=!result;if(!result)return;
 const a=analyzeForecast(result,quote,now),p=a.plan;
 document.getElementById('forecast-brief').textContent=a.summary+(a.band?' Median-Veränderung: '+(a.change>=0?'+':'')+f(a.change)+' %. 10–90%-Szenariospanne am Ende: '+eur(a.band[0])+' bis '+eur(a.band[1])+'.':'');
 document.getElementById('forecast-plan-status').textContent=a.reasons.length?'Abwarten · Bedingungen für ein Szenario nicht erfüllt':p?'Bedingtes '+p.side+'-Szenario · Ausführung und Margin-Verfügbarkeit manuell prüfen':'Kein Positionsszenario verfügbar';
 document.getElementById('forecast-plan-reasons').innerHTML=[...a.reasons,...a.warnings].map(s=>'<li>'+esc(s)+'</li>').join('');
 const row=(label,value)=>'<div class="plan-level"><span>'+label+'</span><strong>'+value+'</strong></div>';
 document.getElementById('forecast-plan-levels').innerHTML=p?row('Richtung',p.side)+row('Entry-Zone',eur(p.zone[0])+' – '+eur(p.zone[1]))+row('Stop-Loss',eur(p.stop))+row('Take-Profit 1 · 50 % schließen',eur(p.target1))+row('Take-Profit 2 · Rest schließen',eur(p.target2))+row('Geplantes Netto-CRV · 50/50-Ausstieg',f(p.rr)+' : 1')+row('Stop-Abstand inkl. Kostenansatz',f(p.riskPct)+' % des Positionswerts')+row('Spätestens vollständig aussteigen',esc(new Date(p.timeExit).toLocaleString('de-DE')))+row('Entry-Prüfung gültig bis',esc(new Date(p.validUntil).toLocaleTimeString('de-DE'))):'';
 document.getElementById('forecast-plan-method').hidden=!p;
}

import unittest
from unittest.mock import patch
import server


class HistoryTests(unittest.TestCase):
    def test_completed_only_and_exclusive_close_timestamp(self):
        candles = [[0, '9', '11', '8', '10', '2', 59999, '20'], [60000, '1', '1', '1', '12', '3',119999,'30']]
        with patch.object(server, 'upstream', return_value=candles), patch.object(server.time, 'time', return_value=90):
            result = server.read_series('BTCUSDT','1m',0,120000)
        self.assertEqual(result['points'], [{'time':60000,'open':9.0,'high':11.0,'low':8.0,'close':10.0,'baseVolume':2.0,'volume':20.0,'closed':True}])

    def test_pagination_has_no_duplicate_boundary(self):
        first = [[i*60000,'1','1','1','10','1',0,'20'] for i in range(1000)]
        last = [[60000000,'1','1','1','11','1',0,'20']]
        with patch.object(server,'upstream',side_effect=[first,last]) as request:
            result=server.read_series('BTCUSDT','1m',0,60060000)
        self.assertEqual(len(result['points']),1001)
        self.assertEqual(request.call_args_list[1].args[1]['startTime'],60000000)
        self.assertEqual(len({p['time'] for p in result['points']}),1001)

    def test_live_includes_forming_candle(self):
        rows=[[0,'9','11','8','10','2',59999,'20'],[60000,'10','12','9','11','3',119999,'33']]
        with patch.object(server,'upstream',return_value=rows),patch.object(server.time,'time',return_value=90):
            result=server.read_series('BTCUSDT','1m',0,90000,live=True)
        self.assertEqual(len(result['points']),2)
        self.assertTrue(result['points'][0]['closed'])
        self.assertFalse(result['points'][1]['closed'])
        self.assertEqual(result['points'][1]['volume'],33)

    def test_empty_history(self):
        with patch.object(server,'upstream',return_value=[]):
            self.assertEqual(server.read_series('NEWUSDT','1h',0,3600000)['points'],[])


class TransportTests(unittest.TestCase):
    def setUp(self):
        server.CACHE.clear()

    def test_official_host_fallback_on_network_failure(self):
        import io
        import urllib.error
        with patch.object(server.urllib.request,'urlopen',side_effect=[urllib.error.URLError('DNS unavailable'),io.BytesIO(b'{"ok":true}')]) as request,patch.object(server.time,'sleep'):
            data=server.upstream('ping',ttl=0)
        self.assertEqual(data,{'ok':True})
        self.assertEqual(request.call_count,2)
        self.assertTrue(request.call_args_list[1].args[0].full_url.startswith('https://api.binance.com/'))

    def test_no_fallback_to_evade_rate_limit(self):
        import urllib.error
        error=urllib.error.HTTPError('https://data-api.binance.vision',429,'limit',{},None)
        with patch.object(server.urllib.request,'urlopen',side_effect=error) as request,patch.object(server.time,'sleep'):
            with self.assertRaises(urllib.error.HTTPError):
                server.upstream('ping',ttl=0)
        self.assertEqual(request.call_count,1)

    def test_ui_requires_local_server_and_has_no_demo(self):
        import re
        from pathlib import Path
        html=Path('static/index.html').read_text()
        app=Path('static/app.js').read_text()
        ids=set(re.findall(r'id="([^"]+)"',html))
        references=set(re.findall(r"\$\('([^']+)'\)",app))
        self.assertEqual(references-ids,{'clear-measurement'})
        self.assertNotIn('STANDALONE',app)
        self.assertNotIn('demoSeries',app)
        self.assertNotIn('snapshotSeries',app)
        self.assertNotIn('https://data-api.binance.vision',app)


class EndpointTests(unittest.TestCase):
    def handler(self, path):
        handler=object.__new__(server.Handler)
        handler.path=path
        handler.send_json=lambda status,data: setattr(handler,'result',(status,data))
        return handler

    def test_reject_large_request_without_network(self):
        handler=self.handler('/api/history?symbols=BTCUSDT,ETHUSDT&interval=1m&start=0&end=999999999999')
        with patch.object(server,'upstream') as request:
            handler.do_GET()
        self.assertEqual(handler.result[0],400)
        request.assert_not_called()

    def test_market_symbols_parameter_has_no_spaces(self):
        import json
        handler=self.handler('/api/markets')
        with patch.object(server,'upstream',return_value={'symbols':[]}) as request:
            handler.do_GET()
        encoded=request.call_args.args[1]['symbols']
        self.assertNotIn(' ',encoded)
        self.assertEqual(json.loads(encoded),list(server.SYMBOLS))

    def test_binance_error_body_is_visible(self):
        import io
        import urllib.error
        handler=self.handler('/api/markets')
        error=urllib.error.HTTPError('https://example.invalid',400,'bad request',{},io.BytesIO(b'{"code":-1100,"msg":"Illegal characters in parameter symbols"}'))
        with patch.object(server,'upstream',side_effect=error):
            handler.do_GET()
        self.assertEqual(handler.result[0],502)
        self.assertIn('Illegal characters',handler.result[1]['error'])
        self.assertNotIn('Region',handler.result[1]['error'])
        self.assertEqual(handler.result[1]['binanceCode'],-1100)

    def test_single_symbol_is_supported(self):
        handler=self.handler('/api/history?symbols=BTCUSDT&interval=1h&start=0&end=3600000')
        with patch.object(server,'read_series',return_value={'symbol':'BTCUSDT','points':[]}) as request:
            handler.do_GET()
        self.assertEqual(handler.result[0],200)
        self.assertEqual(len(handler.result[1]),1)
        request.assert_called_once()

    def test_markets_include_only_trading_spot(self):
        handler=self.handler('/api/markets')
        with patch.object(server,'upstream',return_value={'symbols':[
            {'symbol':'BTCUSDT','baseAsset':'BTC','quoteAsset':'USDT','status':'TRADING','isSpotTradingAllowed':True},
            {'symbol':'OLDUSDT','status':'BREAK','isSpotTradingAllowed':True}]}):
            handler.do_GET()
        self.assertEqual(handler.result,(200,[{'symbol':'BTCUSDT','base':'BTC','quote':'USDT'}]))


class AnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # macOS's system JavaScript engine; no downloaded test dependency.
        import ctypes
        from pathlib import Path
        cls.ctypes=ctypes
        try:
            cls.js=ctypes.CDLL('/System/Library/Frameworks/JavaScriptCore.framework/JavaScriptCore')
        except OSError:
            raise unittest.SkipTest('JavaScriptCore is unavailable on this OS')
        cls.js.JSGlobalContextCreate.restype=ctypes.c_void_p
        cls.js.JSGlobalContextCreate.argtypes=[ctypes.c_void_p]
        cls.js.JSStringCreateWithUTF8CString.restype=ctypes.c_void_p
        cls.js.JSStringCreateWithUTF8CString.argtypes=[ctypes.c_char_p]
        cls.js.JSEvaluateScript.restype=ctypes.c_void_p
        cls.js.JSEvaluateScript.argtypes=[ctypes.c_void_p]*4+[ctypes.c_int,ctypes.POINTER(ctypes.c_void_p)]
        cls.js.JSValueToBoolean.restype=ctypes.c_bool
        cls.js.JSValueToBoolean.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
        cls.js.JSStringRelease.argtypes=[ctypes.c_void_p]
        cls.ctx=cls.js.JSGlobalContextCreate(None)
        cls.source=Path('static/analysis.js').read_text().replace('export ','')

    def check_js(self,expression):
        script=self.js.JSStringCreateWithUTF8CString((self.source+'\n'+expression).encode())
        error=self.ctypes.c_void_p()
        result=self.js.JSEvaluateScript(self.ctx,script,None,None,1,self.ctypes.byref(error))
        self.js.JSStringRelease(script)
        self.assertFalse(error.value,'JS evaluation threw an exception')
        self.assertTrue(self.js.JSValueToBoolean(self.ctx,result))

    def test_drawing_survives_child_capture_loss_and_unavailable_capture(self):
        from pathlib import Path
        app=Path('static/app.js').read_text()
        fn='function startDrawingGesture('+app.split('function startDrawingGesture(',1)[1].split('async function enterChartFocus(',1)[0]
        setup="""
        const state={series:[{symbol:'BTCUSDT'}],values:[[100]],drawingSync:false,drawingTool:'line',drawings:{}};
        const listeners={},areaListeners={};let saves=0;
        const window={addEventListener:(n,f)=>listeners[n]=f,removeEventListener:n=>delete listeners[n]};
        const svg={_chart:{group:[0],chartKey:'BTCUSDT'}};
        const area={setPointerCapture:()=>{throw Error('not supported')},hasPointerCapture:()=>false,
        querySelectorAll:()=>[svg],addEventListener:(n,f)=>areaListeners[n]=f,removeEventListener:n=>delete areaListeners[n]};
        const $=id=>id==='chart-area'?area:{};
        const indexAt=()=>0,drawingKey=s=>s,drawingPoint=e=>({time:e.x,price:100+e.x});
        const projectDrawing=(d,a)=>({...d,points:d.points.map(p=>({...p}))});
        const renderDrawings=()=>{},saveDrawings=()=>saves++;
        """
        expression="""
        startDrawingGesture({pointerId:7,x:1},svg);
        areaListeners.lostpointercapture({pointerId:7,type:'lostpointercapture',target:svg});
        if(!state.drawingGesture)return false;
        listeners.pointermove({pointerId:7,x:2,preventDefault:()=>{}});
        listeners.pointerup({pointerId:7,type:'pointerup',x:3,preventDefault:()=>{}});
        return !state.drawingGesture&&saves===1&&state.drawings.BTCUSDT[0].points[1].time===3&&Object.keys(listeners).length===0&&Object.keys(areaListeners).length===0;
        """
        for tool in ['line', 'price-range']:
            with self.subTest(tool=tool):
                self.check_js('(function(){'+setup.replace("drawingTool:'line'","drawingTool:'"+tool+"'")+fn+expression+'})()')

    def test_synchronous_drawing_preserves_times_and_relative_prices(self):
        from pathlib import Path
        app=Path('static/app.js').read_text()
        fn=app.split('function projectDrawing(',1)[1].split('function validateDrawings(',1)[0]
        self.check_js('(function(){function projectDrawing('+fn+"const d={id:'test',type:'line',anchor:100000,points:[{time:12,price:101000},{time:15,price:99000}]},p=projectDrawing(d,.2);return p.id===d.id&&p.points[0].time===12&&Math.abs(p.points[0].price-.202)<1e-10&&Math.abs(p.points[1].price-.198)<1e-10&&d.points[0].price===101000;})()")

    def test_price_range_renders_directional_change_and_vertical_selection(self):
        from pathlib import Path
        app=Path('static/app.js').read_text()
        fn='function priceRangeMarkup('+app.split('function priceRangeMarkup(',1)[1].split('function drawingPoint(',1)[0]
        setup="const money=String,pct=n=>(n>=0?'+':'')+n+'%',quote=()=> 'EUR',escape=String;"
        self.check_js('(function(){'+setup+fn+"""
        const chart={w:800,extra:0},x=t=>t,y=p=>202-p;
        const up=priceRangeMarkup([{time:100,price:100},{time:200,price:125}],x,y,chart);
        const down=priceRangeMarkup([{time:200,price:125},{time:100,price:100}],x,y,chart);
        const vertical=priceRangeMarkup([{time:100,price:100},{time:100,price:125}],x,y,chart);
        return up.includes('+25 EUR (+25%)')&&up.includes('#7fdfb8')&&down.includes('-25 EUR (-20%)')&&down.includes('#f48b9c')&&!vertical.includes('NaN')&&!vertical.includes('Infinity')&&vertical.includes('width="1"')&&priceRangeMarkup([{time:100,price:100}],x,y,chart)==='';
        """+'})()')

    def test_price_range_persistence_requires_two_valid_anchors(self):
        from pathlib import Path
        app=Path('static/app.js').read_text()
        fn='function validateDrawings('+app.split('function validateDrawings(',1)[1].split('function saveDrawings(',1)[0]
        self.check_js('(function(){'+fn+"""
        const range={id:'range-1',type:'price-range',points:[{time:1,price:100},{time:2,price:125}]};
        const stored=JSON.parse(JSON.stringify({'bitvavo:BTCUSDT':[range,{...range,points:[range.points[0]]}]}));
        const restored=validateDrawings(stored)['bitvavo:BTCUSDT'];
        return restored.length===1&&restored[0].type==='price-range'&&restored[0].points[1].price===125;
        """+'})()')

    def test_saved_drawings_validate_market_namespace_and_coordinates(self):
        from pathlib import Path
        app=Path('static/app.js').read_text()
        fn=app.split('function validateDrawings(',1)[1].split('function saveDrawings(',1)[0]
        self.check_js('(function(){function validateDrawings('+fn+"const good={id:'draw-1',type:'line',points:[{time:1,price:100}]};const clean=validateDrawings({'bitvavo:BTCUSDT':[good,{...good,id:'<script>'},{...good,points:[{time:1,price:NaN}]},{...good,type:'bad'}],'binance:FETUSDT':[good],'other:BTCUSDT':[good]});return clean['bitvavo:BTCUSDT'].length===1&&clean['binance:FETUSDT'].length===1&&!clean['other:BTCUSDT']&&Object.keys(validateDrawings(null)).length===0;})()")

    def test_drawing_pointer_maps_price_and_percent_scales_to_same_raw_price(self):
        from pathlib import Path
        app=Path('static/app.js').read_text()
        fn=app.split('function drawingPoint(',1)[1].split('function startDrawingGesture(',1)[0]
        setup="const state={times:[1000,2000],values:[[200,220]]};const indexAt=()=>1;const svg={getBoundingClientRect:()=>({top:0,height:320}),_chart:{group:[0],view:[0,1],min:180,max:220,extra:0,percent:false}};"
        self.check_js('(function(){'+setup+'function drawingPoint('+fn+"const raw=drawingPoint({clientY:116},svg);svg._chart={...svg._chart,percent:true,min:-10,max:10};const percent=drawingPoint({clientY:116},svg);return raw.time===2000&&raw.price===200&&percent.price===raw.price;})()")

    def test_research_report_renders_scope_scores_and_escapes_text(self):
        import json
        from pathlib import Path
        source=Path('static/research.js').read_text().replace('export ','').split('let loading=false;')[0]
        factory='new Function("document",'+json.dumps(source+';return renderResearch;')+')'
        script='''(function(){const nodes={};const doc={getElementById:id=>nodes[id]||(nodes[id]={})};
        const render=FACTORY(doc);render({suite:{status:'running',profile:'full',errors:[]},datasets:[{venue:'bitvavo',symbol:'BTCUSDT',quote:'EUR',candles:100,expected:8760,coveragePct:1,longestContiguous:100}],studies:[{venue:'binance',symbol:'FETUSDT',quote:'USDT',profile:'pilot',status:'error',completedWindows:2,plannedWindows:12,error:'<img src=x>',test:{windows:2,modelMAPE:1,baselineMAPE:2}}],journal:{forecasts:1,completedForecasts:0,scoredTargets:0,note:'Noch keine bewerteten Kurse'}});
        return nodes['research-data'].innerHTML.includes('BTC/EUR')&&nodes['research-studies'].innerHTML.includes('FET/USDT')&&nodes['research-studies'].innerHTML.includes('&lt;img')&&!nodes['research-studies'].innerHTML.includes('<img')&&nodes['research-journal'].textContent.includes('0 bewertete Zielkurse');})()'''
        self.check_js(script.replace('FACTORY',factory))

    def forecast_plan_js(self,expression):
        import json
        from pathlib import Path
        source=Path('static/forecast-position.js').read_text().replace('export ','').split('const f=n=>')[0]
        fixture='''const now=200*3600000+300000,asof=200*3600000;
        function fixture(direction=1,move=10){return {quote:'EUR',dataAsOf:asof,generatedAt:now-60000,history:Array.from({length:128},(_,i)=>({time:asof-(127-i)*3600000,high:100.1,low:99.9,close:100})),points:Array.from({length:24},(_,i)=>({time:asof+(i+1)*3600000,median:100+direction*(i+1)*move/24,close:100+direction*(i+1)*move/24,p10:(100+direction*(i+1)*move/24)*.98,p90:(100+direction*(i+1)*move/24)*1.02})),validation:{available:true,beatsBaselineMAE:true}};}
        const quote={price:100,retrievedAt:now};'''
        factory='new Function('+json.dumps(source+'\n'+fixture+'\nreturn '+expression+';')+')'
        self.check_js(factory+'()')

    def test_forecast_plans_have_correct_long_short_levels_and_fixed_entry(self):
        self.forecast_plan_js('''(()=>{const l=analyzeForecast(fixture(),quote,now),s=analyzeForecast(fixture(-1),quote,now),m=analyzeForecast(fixture(),{price:100.03,retrievedAt:now},now);return !l.reasons.length&&!s.reasons.length&&l.plan.stop<l.plan.zone[0]&&l.plan.target1>l.plan.zone[1]&&l.plan.target2>l.plan.target1&&s.plan.stop>s.plan.zone[1]&&s.plan.target2<s.plan.target1&&s.plan.target1<s.plan.zone[0]&&l.plan.rr>=2&&s.plan.rr>=2&&l.plan.entry===m.plan.entry;})()''')

    def test_forecast_plans_reject_costs_and_failed_comparison(self):
        self.forecast_plan_js('''(()=>{const weak=analyzeForecast(fixture(1,.1),quote,now),bad=fixture();bad.validation.beatsBaselineMAE=false;const missing=fixture();delete missing.validation;return weak.reasons.some(s=>s.includes('2:1'))&&analyzeForecast(bad,quote,now).reasons.some(s=>s.includes('Referenz'))&&analyzeForecast(missing,quote,now).reasons.length>0;})()''')

    def test_forecast_plans_reject_stale_quotes_outside_entry_and_old_models(self):
        self.forecast_plan_js('''(()=>{const stale=fixture();stale.generatedAt=now-3600001;return !analyzeForecast(stale,quote,now).plan&&!analyzeForecast(fixture(),{price:100,retrievedAt:now-60001},now).plan&&analyzeForecast(fixture(),{price:104,retrievedAt:now},now).reasons.some(s=>s.includes('Entry-Zone'));})()''')

    def test_forecast_plans_do_not_use_invalid_or_gapped_stop_candles(self):
        self.forecast_plan_js('''(()=>{const gaps=fixture();gaps.history.at(-5).time-=3600000;const wrong=fixture();wrong.quote='USDT';return !analyzeForecast(gaps,quote,now).plan&&!analyzeForecast(wrong,quote,now).plan;})()''')

    def test_app_javascript_syntax(self):
        from pathlib import Path
        import json
        app=Path('static/app.js').read_text().replace("import {align,strongestResistances,oiLiquidationEstimates} from './analysis.js';", '')
        self.check_js('typeof new Function('+json.dumps(app)+') === "function"')

    def test_real_ohlc_and_volume_rendering(self):
        from pathlib import Path
        import json
        app=Path('static/app.js').read_text().replace("import {align,strongestResistances,oiLiquidationEstimates} from './analysis.js';", '').split("$('liquidation-mode').onchange=")[0]
        factory='new Function("document",'+json.dumps(app+';return {state,volumeBars,candleDetails};')+')'
        expression = """(function(){const ui=FACTORY({getElementById:()=>({value:'base'}),addEventListener:()=>{}});Object.assign(ui.state,{mode:'split',markets:[{symbol:'BTCUSDT',base:'BTC',quote:'USDT'}],series:[{symbol:'BTCUSDT'}],times:[0,1],view:[0,1],candles:[[{open:9,high:11,low:8,close:10,baseVolume:2,volume:20},{open:10,high:12,low:9,close:11,baseVolume:4,volume:44}]]});const bars=ui.volumeBars([0],500,0,1);return bars.includes('height="19"')&&bars.includes('height="38"')&&ui.candleDetails(0,0).includes('BTC')&&!bars.includes('NaN');})()"""
        self.check_js(expression.replace('FACTORY',factory))

    def test_measurement_returns_chronological_gain_and_loss(self):
        from pathlib import Path
        import json
        app=Path('static/app.js').read_text()
        start=app.index('function measurementChanges(')
        end=app.index('function renderMeasurement(',start)
        fn=app[start:end]
        self.check_js('(function(){'+fn+'const result=measurementChanges([[100,110,125],[200,190,180]],2,0);return result[0].change===25&&Math.abs(result[1].change+10)<1e-9&&measurementChanges([[100]],0,0)[0].change===0;})()')

    def test_axis_drag_changes_span_and_keeps_center(self):
        from pathlib import Path
        app=Path('static/app.js').read_text()
        fn=app[app.index('function axisRange('):app.index('function measurementChanges(')]
        self.check_js('(function(){'+fn+'const a=axisRange({min:-10,max:30},120),b=axisRange({min:-10,max:30},-120);return Math.abs((a.min+a.max)/2-10)<1e-9&&(a.max-a.min)>40&&(b.max-b.min)<40&&Number.isFinite(axisRange({min:0,max:100},1e9).max);})()')

    def test_button_zoom_preserves_center_and_stays_in_bounds(self):
        from pathlib import Path
        app=Path('static/app.js').read_text()
        fn=app[app.index('function zoomedRange('):app.index('function zoomTime(')]
        self.check_js('(function(){'+fn+'const inside=zoomedRange([20,80],101,.7),outside=zoomedRange([0,100],101,1/.7),edge=zoomedRange([0,20],101,1/.7);return inside[1]-inside[0]===42&&(inside[0]+inside[1])/2===50&&outside[0]===0&&outside[1]===100&&edge[0]===0&&edge[1]<=100;})()')

    def test_zoom_only_updates_target_chart(self):
        from pathlib import Path
        app=Path('static/app.js').read_text()
        fn=app[app.index('function zoomedRange('):app.index('function axisRange(')]
        setup="const state={times:Array.from({length:101},(_,i)=>i),axisRanges:{},chartViews:{}};function setChartView(key,view){state.chartViews[key]=view}function renderCharts(){}function renderCards(){};"
        self.check_js('(function(){'+setup+fn+'state.chartViews.ETHUSDT=[0,100];state.axisRanges.eth={min:10,max:20};zoomTime(.7,{min:0,max:100,rangeKey:"btc",chartKey:"BTCUSDT",view:[0,100]});return state.chartViews.BTCUSDT[1]-state.chartViews.BTCUSDT[0]===70&&state.chartViews.ETHUSDT[0]===0&&state.chartViews.ETHUSDT[1]===100&&state.axisRanges.eth.min===10&&state.axisRanges.eth.max===20;})()')

    def test_sync_zoom_copies_time_and_relative_axis_settings(self):
        from pathlib import Path
        app=Path('static/app.js').read_text()
        view=app[app.index('function setChartView('):app.index('function indexAt(')]
        axis=app[app.index('function setAxisRange('):app.index('function zoomTime(')]
        setup="const state={syncZoom:true,mode:'split',series:[{symbol:'BTCUSDT'},{symbol:'ETHUSDT'}],times:[100,200,300],chartViews:{},syncAxis:{}};const $=()=>({value:'price'});"
        self.check_js('(function(){'+setup+view+axis+'setChartView("BTCUSDT",[0,1]);setAxisRange({baseMin:0,baseMax:100},{min:25,max:75});return state.chartViews.BTCUSDT[1]===200&&state.chartViews.ETHUSDT[1]===200&&state.syncAxis.price.factor===.5&&state.syncAxis.price.offset===0;})()')

    def test_resistance_zones_use_confirmed_repeated_highs(self):
        self.check_js("(function(){const highs=[90,100,90,89,100.2,90,88,101,89];const points=highs.map((high,i)=>({time:i,high,close:95,closed:true}));const zones=resistanceZones(points,1,.3,2,1);return zones.length===1&&zones[0].touches===2&&zones[0].low===100&&zones[0].high===100.2&&zones[0].distance>5;})()")

    def test_resistance_ignores_unconfirmed_high_and_broken_zones(self):
        self.check_js("(function(){const p=[90,100,90,100,90].map((high,i)=>({time:i,high,close:101,closed:true}));return resistanceZones(p,1,.3,2,1).length===0&&resistanceZones(p.map((v,i)=>({...v,close:95,closed:i<3})),1,.3,2,1).length===0;})()")

    def test_strongest_resistances_are_ranked_and_limited(self):
        self.check_js("(function(){const p=Array.from({length:200},(_,i)=>({time:i,high:i%10===4?100+(Math.floor(i/10)%5)*5:80,low:75,close:79,volume:100,closed:true}));const z=strongestResistances(p,1);return z.length===3&&z.every((v,i)=>v.rank===i+1&&v.touches>=2)&&(z[0].score>=z[1].score);})()")

    def test_pan_preserves_span_and_clamps_to_loaded_history(self):
        from pathlib import Path
        app=Path('static/app.js').read_text()
        fn=app[app.index('function pannedRange('):app.index('function startPan(')]
        self.check_js('(function(){'+fn+'const a=pannedRange([20,40],101,50,100),b=pannedRange([20,40],101,-1000,100),c=pannedRange([0,100],101,50,100);return a[0]===10&&a[1]===30&&b[0]===80&&b[1]===100&&c[0]===0&&c[1]===100;})()')

    def test_estimated_liquidations_are_explicit_relative_scenarios(self):
        self.check_js("(function(){const p=Array.from({length:12},(_,i)=>({time:i,open:100,high:100.1,low:99.9,close:100,volume:1000,closed:true}));const zones=estimatedLiquidations(p);return zones.length===6&&zones.every(z=>z.kind==='estimated'&&z.notional===undefined&&z.intensity>0&&z.intensity<=1)&&(zones.filter(z=>z.side==='long').every(z=>z.high<100))&&(zones.filter(z=>z.side==='short').every(z=>z.low>100));})()")

    def test_estimated_empty_and_zero_volume(self):
        self.check_js("estimatedLiquidations([]).length===0&&estimatedLiquidations(Array.from({length:10},(_,i)=>({time:i,close:100,high:101,low:99,volume:0}))).length===0")

    def test_vertical_pan_preserves_scale_and_moves_both_directions(self):
        from pathlib import Path
        app=Path('static/app.js').read_text()
        fn=app[app.index('function pannedAxisRange('):app.index('function startPan(')]
        self.check_js('(function(){'+fn+'const down=pannedAxisRange({min:100,max:200},50,100),up=pannedAxisRange({min:100,max:200},-50,100),percent=pannedAxisRange({min:-5,max:5},20,200);return down.min===150&&down.max===250&&up.min===50&&up.max===150&&percent.min===-4&&percent.max===6;})()')

    def test_oi_model_does_not_invent_initial_positions_or_exceed_oi(self):
        self.check_js("(function(){const c={step:1,period:'1h',currentCoins:120,markPrice:100,points:[{time:0,coins:100},{time:1,coins:110},{time:2,coins:120}],marks:[{time:0,low:99.9,high:100.1,close:100},{time:1,low:99.9,high:100.1,close:100},{time:2,low:99.9,high:100.1,close:100}]};const m=oiLiquidationEstimates(c);return m.zones.length>0&&Math.abs(m.coverage.long-20/120)<1e-9&&m.unassigned.long>=9999&&m.zones.every(z=>z.lowNotional<=z.estimatedNotional&&z.highNotional>=z.estimatedNotional)&&m.zones.filter(z=>z.side==='long').reduce((s,z)=>s+z.quantity,0)<=120;})()")

    def test_no_oi_increase_produces_no_invented_zones(self):
        self.check_js("(function(){const points=[0,1,2].map(time=>({time,coins:100})),marks=[0,1,2].map(time=>({time,low:99,high:101,close:100}));const m=oiLiquidationEstimates({step:1,currentCoins:100,markPrice:100,points,marks});return m.zones.length===0&&m.coverage.long===0&&m.unassigned.long===10000;})()")

    def test_model_discards_crossed_long_thresholds(self):
        self.check_js("(function(){const m=oiLiquidationEstimates({step:1,currentCoins:110,markPrice:100,points:[{time:0,coins:100},{time:1,coins:110},{time:2,coins:110}],marks:[{time:0,low:99,high:101,close:100},{time:1,low:99,high:101,close:100},{time:2,low:50,high:101,close:100}]});return m.zones.filter(z=>z.side==='long').length===0;})()")

    def position_js(self, expression):
        from pathlib import Path
        self.check_js(Path('static/positions-model.js').read_text().replace('export ', '')+'\n'+expression)

    def test_positions_page_module_syntax_and_controls(self):
        from pathlib import Path
        import json, re
        script=Path('static/kronos.js').read_text()
        plain=re.sub(r'^import .*?;\n','',script,flags=re.M)
        self.check_js('typeof new Function('+json.dumps(plain)+') === "function"')
        html=Path('static/positions.html').read_text()
        self.assertFalse(set(re.findall(r"\$\('([^']+)'\)",script))-set(re.findall(r'id="([^"]+)"',html)))
        self.assertIn('/positions.html',Path('static/index.html').read_text())
        self.assertNotIn('<input',html)
        self.check_js('typeof new Function('+json.dumps(Path('static/kronos-chart.js').read_text().replace('export ',''))+') === "function"')

    def test_position_chart_has_future_zone_and_excludes_rejected_plans(self):
        from pathlib import Path
        script=Path('static/position-chart.js').read_text().replace('export ', '')
        self.check_js(script+""";(function(){const points=[{time:0,open:100,high:102,low:99,close:101}];const plan={side:'long',entry:102,stop:98,targets:[{low:110,high:111}]};const plotted=positionChart(points,101,[plan]),empty=positionChart(points,101,[{...plan,reason:'no setup'}]);return plotted.includes('LONG Ziel 1')&&plotted.includes('Zeitpunkt offen')&&!plotted.includes('NaN')&&!empty.includes('LONG Ziel 1')&&positionChart([],101,[])==='';})()""")

    def test_detailed_kronos_report_syntax_and_element_ids(self):
        from pathlib import Path
        import json,re
        script=Path('static/kronos-report.js').read_text().replace('export ','')
        self.check_js('typeof new Function('+json.dumps(script)+') === "function"')
        html=Path('static/positions.html').read_text()
        self.assertFalse(set(re.findall(r"\$\('([^']+)'\)",script))-set(re.findall(r'id="([^"]+)"',html)))

    def test_positions_budget_and_zero_risk_rejection(self):
        self.position_js("positionPlans([],[],{risk:0}).plans.length===0&&positionPlans([],[],{risk:6}).error!==null&&positionPlans([],[],{risk:1,dailyLoss:4,openRisk:1}).error!==null")

    def test_positions_size_capped_and_targets_on_correct_side(self):
        self.position_js("""(function(){const p=Array.from({length:60},(_,i)=>({time:i,close:100+i,high:101+i,low:99+i,closed:true}));const z=[{side:'short',low:180,high:181,estimatedNotional:1000},{side:'long',low:90,high:91}];const r=positionPlans(p,z,{risk:5,dailyLoss:3,openRisk:1,capital:100,leverage:3,cost:.5,step:1});const a=r.plans[0];return r.budget===1&&!a.reason&&a.stop<a.entry&&a.targets.every(t=>t.price>a.entry)&&a.plannedLoss<=1.00000001&&a.notional<=300&&r.plans[1].reason!==null;})()""")

    def test_positions_refuse_gaps_and_missing_liquidation_targets(self):
        self.position_js("""(function(){const p=Array.from({length:60},(_,i)=>({time:i,close:100+i,high:101+i,low:99+i,closed:true}));const noTargets=positionPlans(p,[],{step:1});p[40].time+=.5;return noTargets.plans.every(p=>p.reason)&&positionPlans(p,[],{step:1}).error.includes('Datenlücken');})()""")

    def test_positions_reversal_requires_sweep_and_return(self):
        self.position_js("""(function(){const p=Array.from({length:60},(_,i)=>({time:i,close:100,high:101,low:99,closed:true}));const z=[{side:'short',low:120,high:121},{side:'long',low:80,high:81}];const a=positionPlans(p,z,{strategy:'reversal',step:1});p[59]={time:59,close:100,high:101,low:97,closed:true};const b=positionPlans(p,z,{strategy:'reversal',step:1});return a.plans.every(p=>p.reason)&&!b.plans[0].reason&&b.plans[1].reason!==null;})()""")

    def test_alignment_uses_intersection(self):
        self.check_js("JSON.stringify(align([{points:[{time:1,close:2},{time:2,close:3}]},{points:[{time:2,close:4},{time:3,close:5}]}]))===JSON.stringify({times:[2],values:[[3],[4]]})")

    def test_opposite_and_same_returns(self):
        self.check_js("scanPatterns([0,1,2],[[100,102,104],[100,98,96]],1,1,1).hits.every(h=>h.type==='opposite') && scanPatterns([0,1,2],[[100,102,104],[200,204,208]],1,1,1).hits.length===2")

    def test_lag_finds_delayed_return_series(self):
        self.check_js("(function(){const times=Array.from({length:100},(_,i)=>i),a=[100],b=[100];const r=i=>.01*Math.sin(i*1.71)+.005*Math.cos(i*i*.17);for(let i=1;i<100;i++){a.push(a[i-1]*(1+r(i)));b.push(b[i-1]*(1+r(i-3)))}const lag=lagCorrelation(times,a,b,1);return lag.lag===3&&lag.correlation>.999&&lag.n>=30;})()")

    def test_lag_requires_minimum_observations(self):
        self.check_js("lagCorrelation([0,1,2],[100,102,101],[100,102,101],1)===null")

    def test_gaps_are_not_scanned(self):
        self.check_js("scanPatterns([0,1,3],[[100,102,104],[100,103,107]],2,1,1).pairs[0].tested===0")

    def test_percent_difference_and_constant_correlation(self):
        self.check_js("Math.abs(scanPatterns([0,1],[[100,110],[100,100]],1,2,1).hits[0].x-10)<1e-9 && correlation([0,0,0],[1,2,3])===null")

    def test_non_overlapping_windows(self):
        self.check_js("scanPatterns([0,1,2,3,4],[[100,102,104,106,108],[100,102,104,106,108]],2,1,1).pairs[0].tested===2")

class SnapshotTests(unittest.TestCase):
    def test_saved_binance_ohlc_and_volumes(self):
        import json
        from pathlib import Path
        data=json.loads(Path('static/binance-snapshot.json').read_text())
        self.assertEqual(data['source'],'Binance ChatGPT Plugin')
        self.assertEqual({m['symbol'] for m in data['markets']},set(server.SYMBOLS))
        self.assertEqual(len(data['series']),5)
        for series in data['series']:
            self.assertGreater(len(series['points']),100)
            for p in series['points']:
                self.assertLessEqual(p['low'],min(p['open'],p['close']))
                self.assertGreaterEqual(p['high'],max(p['open'],p['close']))
                self.assertGreaterEqual(p['baseVolume'],0)
                self.assertGreaterEqual(p['volume'],0)

if __name__=='__main__':
    unittest.main()

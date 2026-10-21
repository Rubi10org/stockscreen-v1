import io
import unittest
from unittest.mock import patch
import urllib.error
import server
import test_server


class BitvavoTests(unittest.TestCase):
    def test_markets_only_active_eur_pairs(self):
        rows=[{'market':'BTC-EUR','base':'BTC','quote':'EUR','status':'trading'},
              {'market':'FET-EUR','base':'FET','quote':'EUR','status':'halted'},
              {'market':'BTC-USDC','base':'BTC','quote':'USDC','status':'trading'}]
        with patch.object(server,'upstream',return_value=rows):
            result=server.bitvavo_markets()
        self.assertEqual(result,[{'symbol':'BTCUSDT','market':'BTC-EUR','base':'BTC','quote':'EUR'}])

    def test_reverse_order_forming_and_estimated_turnover(self):
        rows=[[60000,'10','12','9','11','3'],[0,'9','11','8','10','2']]
        with patch.object(server,'upstream',return_value=rows),patch.object(server.time,'time',return_value=90):
            completed=server.bitvavo_series('BTCUSDT','1m',0,90000)
            live=server.bitvavo_series('BTCUSDT','1m',0,90000,True)
        self.assertEqual([p['time'] for p in completed['points']],[60000])
        self.assertEqual([p['time'] for p in live['points']],[60000,120000])
        self.assertFalse(live['points'][1]['closed'])
        self.assertEqual(live['points'][1]['baseVolume'],3)
        self.assertEqual(live['points'][1]['volume'],33)
        self.assertTrue(live['points'][1]['quoteVolumeEstimated'])
        self.assertEqual(live['quote'],'EUR')

    def test_sparse_windows_continue_without_filling_gaps(self):
        batches=[[[0,'1','1','1','1','2']],[[60000000,'1','1','1','1','3']]]
        with patch.object(server,'upstream',side_effect=batches) as request:
            result=server.bitvavo_series('FETUSDT','1m',0,60060000)
        self.assertEqual(len(result['points']),2)
        self.assertEqual(request.call_args_list[1].args[1]['start'],60000000)
        self.assertEqual(request.call_args_list[0].args[0],'FET-EUR/candles')
        self.assertEqual(request.call_args_list[1].args[1]['end']%60000,0)

    def test_public_transport_no_credentials_or_binance_fallback(self):
        server.CACHE.clear()
        with patch.object(server,'bitvavo_json',return_value=[]) as request:
            server.upstream('markets',source='bitvavo',ttl=0)
        self.assertEqual(request.call_args.args[0],'https://api.bitvavo.com/v2/markets')
        server.CACHE.clear()
        with patch.object(server,'bitvavo_json',side_effect=urllib.error.URLError('DNS')) as request:
            with self.assertRaises(urllib.error.URLError):
                server.upstream('markets',source='bitvavo')
        self.assertEqual(request.call_count,1)

    def test_history_dispatch_and_source_validation(self):
        handler=test_server.EndpointTests().handler('/api/history?source=bitvavo&symbols=BTCUSDT&interval=1h&start=0&end=3600000')
        with patch.object(server,'bitvavo_series',return_value={'symbol':'BTCUSDT','points':[]}) as bitvavo,patch.object(server,'read_series') as binance:
            handler.do_GET()
        self.assertEqual(handler.result[0],200)
        bitvavo.assert_called_once()
        binance.assert_not_called()
        handler=test_server.EndpointTests().handler('/api/markets?source=invalid')
        handler.do_GET()
        self.assertEqual(handler.result[0],400)

    def test_bitvavo_errors_are_named(self):
        handler=test_server.EndpointTests().handler('/api/markets?source=bitvavo')
        error=urllib.error.HTTPError('https://api.bitvavo.com',429,'limit',{},io.BytesIO(b'{"error":"Slow down"}'))
        with patch.object(server,'bitvavo_markets',side_effect=error):
            handler.do_GET()
        self.assertEqual(handler.result[0],502)
        self.assertIn('Bitvavo',handler.result[1]['error'])
        self.assertIn('Slow down',handler.result[1]['error'])


class LoadingRegressionTests(unittest.TestCase):
    def test_health_announces_bitvavo_support(self):
        handler=test_server.EndpointTests().handler('/api/health')
        handler.do_GET()
        self.assertEqual(handler.result[0],200)
        self.assertIn('bitvavo',handler.result[1]['sources'])
        self.assertEqual(handler.result[1]['version'],'bitvavo-2')

    def test_slow_futures_does_not_block_bitvavo(self):
        from threading import Event, Thread
        started, release, completed = Event(), Event(), Event()
        errors=[]
        server.CACHE.clear()
        def response(request, **kwargs):
            if request.full_url.startswith('https://fapi.binance.com/'):
                started.set()
                if not release.wait(3):
                    raise TimeoutError('Test cleanup timeout')
            return io.BytesIO(b'[]')
        def fetch(source, futures=False):
            try:
                server.upstream('loading-regression',source=source,futures=futures,ttl=0)
                if source=='bitvavo': completed.set()
            except Exception as error:
                errors.append(error)
        with patch.object(server.urllib.request,'urlopen',side_effect=response),patch.object(server,'bitvavo_json',return_value=[]),patch.object(server.time,'sleep'):
            futures_thread=Thread(target=fetch,args=('binance',True))
            bitvavo_thread=Thread(target=fetch,args=('bitvavo',))
            futures_thread.start()
            try:
                self.assertTrue(started.wait(1))
                bitvavo_thread.start()
                self.assertTrue(completed.wait(1),'Bitvavo wartet auf Binance Futures')
            finally:
                release.set()
                futures_thread.join(3)
                if bitvavo_thread.ident: bitvavo_thread.join(3)
        self.assertEqual(errors,[])


class CurlTransportTests(unittest.TestCase):
    def test_json_success_and_secure_bounded_arguments(self):
        result=server.subprocess.CompletedProcess([],0,stdout=b'[{"market":"BTC-EUR"}]\n200',stderr=b'')
        with patch.object(server.shutil,'which',return_value='/usr/bin/curl'),patch.object(server.subprocess,'run',return_value=result) as run:
            data=server.bitvavo_json('https://api.bitvavo.com/v2/markets')
        self.assertEqual(data,[{'market':'BTC-EUR'}])
        args=run.call_args.args[0]
        self.assertIn('--max-time',args)
        self.assertNotIn('--insecure',args)
        self.assertNotIn('-k',args)
        self.assertNotIn('shell',run.call_args.kwargs)
        self.assertEqual(run.call_args.kwargs['timeout'],15)

    def test_http_failure_preserves_provider_detail(self):
        result=server.subprocess.CompletedProcess([],0,stdout=b'{"error":"Rate limit"}\n429',stderr=b'')
        with patch.object(server.shutil,'which',return_value='/usr/bin/curl'),patch.object(server.subprocess,'run',return_value=result):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                server.bitvavo_json('https://api.bitvavo.com/v2/markets')
        self.assertEqual(caught.exception.code,429)
        self.assertIn(b'Rate limit',caught.exception.read())

    def test_network_failure_is_explicit(self):
        result=server.subprocess.CompletedProcess([],28,stdout=b'\n000',stderr=b'Connection timed out')
        with patch.object(server.shutil,'which',return_value='/usr/bin/curl'),patch.object(server.subprocess,'run',return_value=result):
            with self.assertRaises(urllib.error.URLError) as caught:
                server.bitvavo_json('https://api.bitvavo.com/v2/markets')
        self.assertIn('Connection timed out',str(caught.exception))


class PriceEndpointTests(unittest.TestCase):
    def test_ticker_object_and_array_responses(self):
        for payload in ({'market':'BTC-EUR','price':'60000'},[{'market':'BTC-EUR','price':'60000'}]):
            handler=test_server.EndpointTests().handler('/api/price?source=bitvavo&symbol=BTCUSDT')
            with patch.object(server,'upstream',return_value=payload):
                handler.do_GET()
            self.assertEqual(handler.result[0],200)
            self.assertEqual(handler.result[1]['price'],60000)
            self.assertEqual(handler.result[1]['quote'],'EUR')
            self.assertIn('retrievedAt',handler.result[1])

    def test_rejects_invalid_price_and_wrong_market(self):
        for payload in ({'market':'BTC-EUR','price':'NaN'},{'market':'FET-EUR','price':'1'}):
            handler=test_server.EndpointTests().handler('/api/price?source=bitvavo&symbol=BTCUSDT')
            with patch.object(server,'upstream',return_value=payload):
                handler.do_GET()
            self.assertEqual(handler.result[0],400)

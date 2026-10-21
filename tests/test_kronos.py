import json
import subprocess
import time
import unittest
from unittest.mock import patch
import kronos_service as service
import server
from kronos_config import MODEL_REVISION, SEEDS, MODEL_ID


def history():
    now=int(time.time()*1000)//3600000*3600000
    return [{'time':now-(255-i)*3600000,'open':100,'high':102,'low':98,'close':101,'closed':True} for i in range(256)]


class KronosTests(unittest.TestCase):
    def test_history_rejects_gaps_and_stale_data(self):
        points=history();now=int(time.time()*1000)
        self.assertEqual(len(service.validate_history(points,now)),256)
        with self.assertRaises(ValueError): service.validate_history(points,now+3*3600000)
        points[200]['time']+=1
        with self.assertRaises(ValueError): service.validate_history(points,now)

    def test_forming_candle_and_invalid_prices_excluded(self):
        points=history();points.append({**points[-1],'time':points[-1]['time']+3600000,'closed':False})
        self.assertEqual(len(service.validate_history(points,int(time.time()*1000))),256)
        points[100]['high']=float('nan')
        with self.assertRaises(ValueError): service.validate_history(points,int(time.time()*1000))

    def test_missing_model_never_returns_fake_forecast(self):
        jobs=service.KronosJobs()
        with patch.object(service,'installation_status',return_value={'installed':False,'missing':['Modell']}):
            with self.assertRaisesRegex(ValueError,'Setup-Kronos'): jobs.start('BTCUSDT',lambda *a:None)
        self.assertEqual(jobs.jobs,{})

    def test_jobs_run_in_background_and_reuse_active_coin(self):
        jobs=service.KronosJobs()
        with patch.object(service,'installation_status',return_value={'installed':True}),patch.object(service.threading,'Thread') as thread:
            a=jobs.start('BTCUSDT',lambda *a:None)
            b=jobs.start('BTCUSDT',lambda *a:None)
            self.assertEqual(a['id'],b['id'])
            self.assertEqual(thread.call_count,1)
            with self.assertRaises(ValueError): jobs.start('FETUSDT',lambda *a:None)
        self.assertEqual(jobs.get(a['id'])['status'],'running')

    def test_worker_failure_and_timeout_clear_busy_state(self):
        for failure in (subprocess.TimeoutExpired('python',300),RuntimeError('worker error')):
            jobs=service.KronosJobs();jobs.jobs['test']={'status':'running'};jobs.active='test'
            with patch.object(service.subprocess,'run',side_effect=failure):
                jobs.run('test','BTCUSDT',lambda *a:{'points':history()})
            self.assertEqual(jobs.get('test')['status'],'error')
            self.assertIsNone(jobs.active)
            self.assertNotIn('result',jobs.get('test'))

    def test_success_labels_model_data_as_forecast(self):
        jobs=service.KronosJobs();jobs.jobs['test']={'status':'running'};jobs.active='test'
        output={'points':[{'time':history()[-1]['time']+(i+1)*3600000,'close':101,'low':100,'high':102,'median':101,'p10':100.2,'p90':101.8,'ohlc':{'open':100,'high':102,'low':98,'close':101},'validOHLC':True} for i in range(24)],'sampleCount':len(SEEDS),'model':MODEL_ID,'modelRevision':MODEL_REVISION,'parameters':{'context':256},'paths':[[101]*24 for _ in SEEDS]}
        process=subprocess.CompletedProcess([],0,stdout=json.dumps(output),stderr='')
        with patch.object(service.subprocess,'run',return_value=process):
            jobs.run('test','FETUSDT',lambda *a:{'points':history()})
        result=jobs.get('test')['result']
        self.assertEqual(result['market'],'FET-EUR')
        self.assertEqual(result['quote'],'EUR')
        self.assertEqual(result['horizonHours'],24)
        self.assertEqual(len(result['history']),256)


class GapRecoveryTests(unittest.TestCase):
    def test_earlier_gap_uses_latest_contiguous_context(self):
        points=history();del points[50]
        result=service.validate_history(points,int(time.time()*1000))
        self.assertEqual(len(result),205)
        self.assertEqual(result[0]['time'],history()[51]['time'])

    def test_targeted_retry_recovers_real_missing_candle(self):
        points=history();missing=points.pop(200)
        calls=[]
        def reader(symbol,interval,start,end,live):
            calls.append((start,end))
            return {'points':[missing]}
        selected,quality=service.recover_history('BTCUSDT',reader,points,int(time.time()*1000))
        self.assertEqual(len(selected),256)
        self.assertEqual(quality['recoveredCandles'],1)
        self.assertEqual(calls,[(missing['time']-3600000,missing['time'])])

    def test_failed_retry_never_fills_prices(self):
        points=history();del points[100]
        def reader(*args): raise TimeoutError('offline')
        selected,quality=service.recover_history('BTCUSDT',reader,points,int(time.time()*1000))
        self.assertEqual(len(selected),155)
        self.assertEqual(quality['recoveredCandles'],0)
        self.assertEqual(quality['excludedEarlierCandles'],100)

    def test_recent_gap_still_refuses_too_short_history(self):
        points=history();del points[240]
        with self.assertRaisesRegex(ValueError,'nur 15'):
            service.recover_history('BTCUSDT',lambda *a:{'points':[]},points,int(time.time()*1000))

    def test_unsorted_duplicate_input_is_normalized(self):
        points=history()
        result=service.validate_history(list(reversed(points))+[points[50]],int(time.time()*1000))
        self.assertEqual(len(result),256)
        self.assertEqual(result,points)

class DataIntegrityTests(unittest.TestCase):
    def test_conflicting_duplicate_candle_is_rejected(self):
        p=history()
        with self.assertRaisesRegex(ValueError,'Widersprüchliche'):
            service.validate_history(p+[{**p[30],'close':100}],int(time.time()*1000))

    def test_latest_missing_closed_hour_is_retried(self):
        p=history();last=p.pop()
        selected,quality=service.recover_history('BTCUSDT',lambda *a:{'points':[last]},p,int(time.time()*1000))
        self.assertEqual(selected[-1]['time'],last['time'])
        self.assertEqual(quality['recoveredCandles'],1)

    def test_old_last_hour_is_not_presented_as_fresh(self):
        p=history()
        now=p[-1]['time']+3600000+180000
        with self.assertRaisesRegex(ValueError,'veraltet'):
            service.validate_history(p,now)


class ShortContextTests(unittest.TestCase):
    def test_61_real_contiguous_candles_are_accepted_without_filling(self):
        p=history();del p[194]
        selected,quality=service.recover_history('BTCUSDT',lambda *a:{'points':[]},p,int(time.time()*1000))
        self.assertEqual(len(selected),61)
        self.assertEqual(selected,p[-61:])
        self.assertTrue(quality['contextReduced'])
        self.assertEqual(quality['minimumContext'],32)
        self.assertEqual(quality['recoveredCandles'],0)

    def test_below_local_minimum_is_still_rejected(self):
        p=history();del p[224]
        with self.assertRaisesRegex(ValueError,'mindestens 32'):
            service.validate_history(p,int(time.time()*1000))


class CancellationTests(unittest.TestCase):
    def test_cancel_before_inference_never_starts_worker(self):
        import tempfile
        from pathlib import Path
        jobs=service.KronosJobs();jobs.jobs['cancel-test']={'status':'running','stage':'loading'};jobs.active='cancel-test'
        with tempfile.TemporaryDirectory() as directory,patch.object(service,'ROOT',Path(directory)),patch.object(service.subprocess,'run') as process:
            jobs.cancel('cancel-test')
            self.assertTrue(jobs.get('cancel-test')['cancelRequested'])
            jobs.run('cancel-test','BTCUSDT',lambda *a:{'points':history()})
            process.assert_not_called()
            self.assertEqual(jobs.get('cancel-test')['status'],'cancelled')
            self.assertIsNone(jobs.active)
            self.assertFalse((Path(directory)/'data/kronos-progress/cancel-test.cancel').exists())

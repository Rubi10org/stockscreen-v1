import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import research
import research_journal as journal
from research_data import ResearchStore,STEP,binance_rows,timestamp_ms


def points(count,start=0):
    return [{'time':start+(i+1)*STEP,'open':100,'high':102,'low':98,'close':101,'baseVolume':2,'closed':True} for i in range(count)]


class ResearchTests(unittest.TestCase):
    def test_storage_preserves_venue_currency_gaps_and_native_volume(self):
        with tempfile.TemporaryDirectory() as folder:
            store=ResearchStore(Path(folder)/'db.sqlite3')
            sample=points(4);del sample[2]
            store.ingest('bitvavo','BTCUSDT','EUR',sample,'test')
            store.ingest('binance','BTCUSDT','USDT',points(4),'test2')
            self.assertEqual(len(store.points('bitvavo','BTCUSDT','USDT')),0)
            stored=store.points('bitvavo','BTCUSDT','EUR')
            self.assertIsNone(stored[0]['quoteVolume'])
            report=store.summary('bitvavo','BTCUSDT','EUR',0,4*STEP)
            self.assertEqual((report['missing'],report['longestContiguous']),(1,2))

    def test_binance_units_and_real_quote_amount(self):
        opened=1760983200000
        for unit in (opened,opened*1000,opened//1000):
            self.assertEqual(timestamp_ms(unit),opened)
            parsed=binance_rows([[unit,100,102,98,101,3,0,304]],opened,opened+STEP)
            self.assertEqual(parsed[0]['quoteVolume'],304)
            self.assertEqual(parsed[0]['time'],opened+STEP)

    def test_chronological_windows_nonoverlap_and_no_future_inputs(self):
        data=points(8760);windows=research.chronological_windows(data,20)
        previous_end=0
        for phase in ('selection','calibration','test'):
            chosen=windows[phase]
            self.assertEqual(len(chosen),20)
            self.assertTrue(all(b-a>=24 for a,b in zip(chosen,chosen[1:])))
            self.assertGreater(chosen[0],previous_end)
            previous_end=chosen[-1]+23
            for cut in chosen:
                self.assertLess(data[cut-1]['time'],data[cut]['time'])
                self.assertEqual(len(data[cut-512:cut]),512)
        with self.assertRaises(ValueError):research.chronological_windows(points(1000),20)

    def test_calibration_refuses_two_window_pilot(self):
        self.assertFalse(research.calibration_margins([{},{}])['available'])
        rows=[{'score':{'horizons':{h:{'nonconformity':.02} for h in ('1','4','12','24')}}} for _ in range(20)]
        self.assertEqual(research.calibration_margins(rows)['margins']['24'],.02)

    def test_journal_excludes_prepublication_and_wrong_venue_prices(self):
        with tempfile.TemporaryDirectory() as folder:
            store=ResearchStore(Path(folder)/'db.sqlite3')
            result={'generatedAt':STEP+100,'dataAsOf':STEP,'symbol':'BTCUSDT','history':points(1),
                'points':[{'time':i*STEP,'close':101,'p10':100,'p90':102} for i in (1,2,3)]}
            with patch.object(journal,'ResearchStore',return_value=store):journal.record_forecast('live',result)
            store.ingest('binance','BTCUSDT','USDT',points(3),'wrong')
            journal.score_available(store,4*STEP)
            with store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM scores').fetchone()[0],0)
            store.ingest('bitvavo','BTCUSDT','EUR',points(3),'real')
            journal.score_available(store,2*STEP)
            with store.connect() as db:
                self.assertEqual(db.execute('SELECT time FROM scores').fetchall(),[(2*STEP,)])
                self.assertEqual(db.execute('SELECT count(*) FROM journal_status').fetchone()[0],0)
            journal.score_available(store,3*STEP)
            with store.connect() as db:
                self.assertEqual(db.execute('SELECT count(*) FROM scores').fetchone()[0],2)
                self.assertEqual(db.execute('SELECT complete FROM journal_status').fetchone()[0],1)

    def test_resume_reuses_windows_and_freezes_period(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);store=ResearchStore(root/'db.sqlite3');data=points(1000)
            store.ingest('binance','BTCUSDT','USDT',data,'fixture')
            (root/'period.json').write_text(json.dumps({'start':0,'end':1000*STEP}))
            calls=[]
            def predict(request,cache):
                observed=request['points'];calls.append(observed[-1]['time']);last=observed[-1]['time']
                return {'paths':[[101]*24],'points':[{'time':last+(i+1)*STEP,'close':101,'median':101,'p10':100,'p90':102} for i in range(24)],'modelRevision':'fixture','durationSeconds':0}
            with patch.object(research,'DATA',root),patch.object(research,'ResearchStore',return_value=store),patch('kronos_worker.predict',side_effect=predict):
                first=research.run_study('binance','BTCUSDT','USDT',2,'pilot',[128])
                count=len(calls)
                store.ingest('binance','BTCUSDT','USDT',points(1,1000*STEP),'later')
                second=research.run_study('binance','BTCUSDT','USDT',2,'pilot',[128])
            self.assertEqual(first['id'],second['id'])
            self.assertEqual(len(calls),count)
            self.assertEqual(first['test']['windows'],2)
            self.assertFalse(first['livePolicyChanged'])


if __name__=='__main__':unittest.main()

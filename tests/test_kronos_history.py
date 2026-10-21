import tempfile
from pathlib import Path
import unittest
from kronos_config import STEP
from kronos_service import validate_history,recover_history
from research_data import ResearchStore
from bitvavo_kronos import cached_history


def candles(count=544):
    return [{'time':(i+1)*STEP,'open':100,'high':102,'low':99,'close':101,'baseVolume':3,'closed':True} for i in range(count)]


class MaximumHistoryTests(unittest.TestCase):
    def test_one_missing_hour_preserves_512_real_candles_and_timestamps(self):
        data=candles();del data[-63]
        selected,quality=recover_history('FETUSDT',lambda *args:{'points':[]},data,544*STEP,allow_sparse=True)
        self.assertEqual(len(selected),512)
        self.assertEqual(selected,data[-512:])
        self.assertEqual(quality['missingHours'],1)
        self.assertEqual(quality['contextSpanHours'],513)
        self.assertFalse(quality['contextReduced'])
        self.assertEqual(len(validate_history(data,544*STEP)),62)

    def test_large_outage_still_excludes_earlier_history(self):
        data=candles();del data[-65:-62]
        selected=validate_history(data,544*STEP,allow_sparse=True)
        self.assertEqual(len(selected),62)

    def test_many_single_hour_gaps_do_not_bypass_density_limit(self):
        data=[p for i,p in enumerate(candles()) if i%4!=0]
        with self.assertRaisesRegex(ValueError,'mindestens'):
            validate_history(data,544*STEP,allow_sparse=True)

    def test_cache_uses_real_same_venue_candles_and_fresh_values_win(self):
        with tempfile.TemporaryDirectory() as root:
            store=ResearchStore(Path(root)/'cache.sqlite3');data=candles(10)
            store.ingest('bitvavo','FETUSDT','EUR',data,'old')
            store.ingest('binance','FETUSDT','USDT',candles(11),'other')
            fresh={**data[-1],'close':100}
            result=cached_history(lambda *args:{'points':[fresh]},'FETUSDT','1h',0,11*STEP,store=store)
            self.assertEqual(len(result['points']),10)
            self.assertEqual(result['points'][-1]['close'],100)
            self.assertEqual(result['cachedCandles'],9)

    def test_offline_cache_does_not_relax_freshness_check(self):
        with tempfile.TemporaryDirectory() as root:
            store=ResearchStore(Path(root)/'cache.sqlite3');store.ingest('bitvavo','FETUSDT','EUR',candles(64),'real')
            def offline(*args):raise TimeoutError('offline')
            result=cached_history(offline,'FETUSDT','1h',0,70*STEP,store=store)
            self.assertTrue(result['retrievalWarning'])
            with self.assertRaisesRegex(ValueError,'veraltet'):
                validate_history(result['points'],70*STEP,allow_sparse=True)

import time
import unittest
from unittest.mock import patch
import server


class OIDataTests(unittest.TestCase):
    def test_normalizes_historical_and_current_oi_separately(self):
        now=int(time.time()*1000)
        history=[{'timestamp':now-3600000,'sumOpenInterest':'100','sumOpenInterestValue':'10000'}]
        with patch.object(server,'upstream',side_effect=[history,{'openInterest':'110','time':now}]):
            value=server.open_interest_series('BTCUSDT','1h',now-7200000,now)
        self.assertEqual(value['currentCoins'],110)
        self.assertEqual(value['points'][0]['value'],10000)
        self.assertEqual(value['points'][0]['coins'],100)

    def test_model_uses_mark_price_ohlc(self):
        now=int(time.time()*1000)//3600000*3600000
        history=[{'timestamp':now,'sumOpenInterest':'110','sumOpenInterestValue':'11000'}]
        rows=[[now-3600000,'99','102','98','100',0,now-1]]
        responses=[history,{'openInterest':'110','time':now},{'markPrice':'101','time':now},rows]
        with patch.object(server,'upstream',side_effect=responses) as request:
            result=server.open_interest_series('BTCUSDT','1h',now-3600000,now,True)
        self.assertEqual(result['marks'][0],{'time':now,'open':99,'high':102,'low':98,'close':100})
        self.assertEqual(result['markPrice'],101)
        self.assertEqual(request.call_args_list[-1].args[0],'fapi/v1/markPriceKlines')
        self.assertTrue(request.call_args_list[-1].kwargs['futures'])

    def test_old_history_is_clipped_and_not_fabricated(self):
        now=int(time.time()*1000)
        with patch.object(server,'upstream',return_value={'openInterest':'110','time':now}) as request:
            result=server.open_interest_series('BTCUSDT','1h',now-60*86400000,now-40*86400000)
        self.assertEqual(result['points'],[])
        self.assertTrue(result['historyClipped'])
        self.assertEqual(request.call_count,1)

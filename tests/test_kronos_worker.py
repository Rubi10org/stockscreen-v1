import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import kronos_worker as worker
from kronos_config import SEEDS, BATCH_SIZE, VALIDATION_SAMPLES


class WorkerInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not all(importlib.util.find_spec(m) for m in ('torch','pandas')):
            raise unittest.SkipTest('Mit .kronos-env/bin/python ausführen')
        import pandas as pd
        cls.pd=pd
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor'/'kronos_model'))
        import model
        cls.model=model

    def points(self,volume=True):
        points=[{'time':(i+1)*3600000,'open':99,'high':102,'low':98,'close':100} for i in range(128)]
        if volume:
            for p in points: p['baseVolume']=12
        return points

    def run_model(self,points,**options):
        engine=MagicMock()
        engine.predict_batch.side_effect=lambda dfs,*args,**kwargs:[self.pd.DataFrame([{'open':100,'high':102,'low':98,'close':101} for _ in range(24)]) for _ in dfs]
        with patch.object(self.model.Kronos,'from_pretrained') as model,patch.object(self.model.KronosTokenizer,'from_pretrained') as tokenizer,patch.object(self.model,'KronosPredictor',return_value=engine):
            result=worker.predict({'points':points,**options})
            model.return_value.eval.assert_called_once()
            tokenizer.return_value.eval.assert_called_once()
        return result,engine

    def test_sparse_input_preserves_actual_time_gap_without_padding(self):
        points=self.points();del points[20]
        with self.assertRaises(ValueError):worker.predict({'points':points})
        result,engine=self.run_model(points,allowSparseHistory=True)
        frame=engine.predict_batch.call_args_list[0].args[0][0]
        stamps=engine.predict_batch.call_args_list[0].args[1][0]
        self.assertEqual(len(frame),127)
        self.assertEqual((stamps.iloc[20]-stamps.iloc[19]).total_seconds(),7200)
        self.assertEqual(result['parameters']['context'],127)
        self.assertTrue(result['warnings'])

    def test_gap_in_heldout_targets_skips_misleading_24_hour_check(self):
        points=self.points();del points[-5]
        result,engine=self.run_model(points,allowSparseHistory=True)
        self.assertFalse(result['validation']['available'])
        self.assertEqual(engine.predict_batch.call_count,len(SEEDS)//BATCH_SIZE)

    def test_true_volume_approximate_amount_and_utc_open_timestamps(self):
        points=self.points()
        result,engine=self.run_model(points)
        frames,xs,ys=engine.predict_batch.call_args_list[0].args[:3]
        frame,x,y=frames[0],xs[0],ys[0]
        self.assertEqual(frame['volume'].iloc[0],12)
        self.assertEqual(frame['amount'].iloc[0],12*(99+102+98+100)/4)
        self.assertEqual(x.iloc[0].value//1000000,0)
        self.assertEqual(x.iloc[-1].value//1000000,points[-1]['time']-3600000)
        self.assertEqual(y.iloc[0].value//1000000,points[-1]['time'])
        self.assertEqual(result['points'][0]['time'],points[-1]['time']+3600000)
        self.assertEqual(engine.predict_batch.call_count,(len(SEEDS)+VALIDATION_SAMPLES)//BATCH_SIZE)
        self.assertEqual(result['sampleCount'],64)
        self.assertTrue(result['parameters']['evaluationMode'])

    def test_missing_volume_uses_explicit_ohlc_mode(self):
        result,engine=self.run_model(self.points(False))
        self.assertNotIn('volume',engine.predict_batch.call_args_list[0].args[0][0])
        self.assertIn('ohne Volumen',result['input'])
        self.assertTrue(all(p['validOHLC'] for p in result['points']))

    def test_partial_volume_is_rejected_instead_of_silently_dropped(self):
        points=self.points();del points[20]['baseVolume']
        with self.assertRaisesRegex(ValueError,'unvollständig'):
            worker.predict({'points':points})

    def test_retrospective_check_never_uses_heldout_prices_as_inputs(self):
        points=self.points()
        result,engine=self.run_model(points)
        validation_calls=engine.predict_batch.call_args_list[len(SEEDS)//BATCH_SIZE:]
        self.assertTrue(validation_calls)
        dfs,xs,ys=validation_calls[0].args[:3]
        self.assertEqual(len(dfs[0]),len(points)-24)
        self.assertEqual(xs[0].iloc[-1].value//1000000,points[-25]['time']-3600000)
        self.assertEqual(ys[0].iloc[0].value//1000000,points[-24]['time']-3600000)
        self.assertTrue(result['validation']['available'])
        self.assertEqual(result['validation']['windows'],1)

    def test_gpu_failure_restarts_complete_run_on_cpu(self):
        import torch
        cpu=MagicMock();gpu=MagicMock()
        gpu.predict_batch.side_effect=RuntimeError('MPS operator not implemented')
        cpu.predict_batch.side_effect=lambda dfs,*args,**kwargs:[self.pd.DataFrame([{'open':100,'high':102,'low':98,'close':101} for _ in range(24)]) for _ in dfs]
        with patch.object(torch.cuda,'is_available',return_value=False),patch.object(torch.backends.mps,'is_available',return_value=True),patch.object(torch,'arange',return_value=MagicMock()),patch.object(self.model.Kronos,'from_pretrained'),patch.object(self.model.KronosTokenizer,'from_pretrained'),patch.object(self.model,'KronosPredictor',side_effect=[gpu,cpu]) as predictors:
            result=worker.predict({'points':self.points()})
        self.assertEqual(result['device'],'cpu')
        self.assertEqual(result['sampleCount'],64)
        self.assertTrue(any('kompletter Lauf auf CPU' in warning for warning in result['warnings']))
        self.assertEqual([c.kwargs['device'] for c in predictors.call_args_list],['mps','cpu'])

    def test_memory_pressure_reduces_batch_without_dropping_scenarios(self):
        import torch
        engine=MagicMock();calls=[0]
        def output(dfs,*args,**kwargs):
            calls[0]+=1
            if calls[0]==1: raise RuntimeError('out of memory')
            return [self.pd.DataFrame([{'open':100,'high':102,'low':98,'close':101} for _ in range(24)]) for _ in dfs]
        engine.predict_batch.side_effect=output
        with patch.object(torch.cuda,'is_available',return_value=False),patch.object(torch.backends.mps,'is_available',return_value=False),patch.object(self.model.Kronos,'from_pretrained'),patch.object(self.model.KronosTokenizer,'from_pretrained'),patch.object(self.model,'KronosPredictor',return_value=engine):
            result=worker.predict({'points':self.points()})
        self.assertEqual(result['parameters']['batchSize'],2)
        self.assertEqual(len(result['paths']),64)
        self.assertTrue(result['warnings'])

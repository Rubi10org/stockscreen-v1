"""Largest public Kronos checkpoint; bounded ensemble and reproducible sampling."""
MODEL_ID='NeoQuasar/Kronos-base'
MODEL_FOLDER='base'
MODEL_REVISION='2b554741eca47781b64468546e77fef3e85130e6'
TOKENIZER_ID='NeoQuasar/Kronos-Tokenizer-base'
TOKENIZER_REVISION='0e0117387f39004a9016484a186a908917e22426'
CONTEXT=512
MIN_CONTEXT=32  # local guard, not an upstream architectural requirement
MAX_CONTEXT=512
HORIZON=24
STEP=3600000
SEEDS=tuple(17+104729*i for i in range(64))
BATCH_SIZE=4
VALIDATION_SAMPLES=8
TIMEOUT=1200

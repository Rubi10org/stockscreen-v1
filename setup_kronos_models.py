"""Download the public, safetensors-only model assets into this project."""
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parent
os.environ.setdefault('HF_HOME',str(ROOT/'.kronos-cache'/'huggingface'))
os.environ.setdefault('HF_XET_CACHE',str(ROOT/'.kronos-cache'/'xet'))
os.environ.setdefault('HF_HUB_ETAG_TIMEOUT','15')
os.environ.setdefault('HF_HUB_DOWNLOAD_TIMEOUT','30')
from huggingface_hub import snapshot_download
from kronos_config import MODEL_ID, MODEL_FOLDER, MODEL_REVISION, TOKENIZER_ID, TOKENIZER_REVISION
for repo,folder,revision in [(TOKENIZER_ID,'tokenizer',TOKENIZER_REVISION),(MODEL_ID,MODEL_FOLDER,MODEL_REVISION),('NeoQuasar/Kronos-small','small','901c26c1332695a2a8f243eb2f37243a37bea320')]:
    print('Modell laden: '+repo,flush=True)
    snapshot_download(repo_id=repo,revision=revision,local_dir=str(ROOT/'.kronos-models'/folder),allow_patterns=['config.json','model.safetensors','README.md'])
print('Kronos-Modellgewichte vorhanden.',flush=True)

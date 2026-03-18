#!/bin/bash
# GPU Worker auto-start for Vast.ai (single persistent instance)
# Env vars CPU_API_BASE_URL, GPU_API_KEY, S3_* are passed via vast.ai extra_env
set -e

export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"

need_install=0
command -v git >/dev/null 2>&1 || need_install=1
command -v ffmpeg >/dev/null 2>&1 || need_install=1
command -v python3 >/dev/null 2>&1 || need_install=1
if [ "$need_install" -eq 1 ]; then
  apt-get update -qq
  apt-get install -y -qq git python3-pip python3-venv ffmpeg
fi

REPO_URL="${GIT_REPO_URL:-https://github.com/AziCodder/Clips-AI.git}"
cd /root
if [ ! -d "clips/.git" ]; then
  rm -rf clips
  git clone "$REPO_URL" clips
fi
cd clips
# Optional update; do not fail startup if git is temporarily unavailable.
git pull --ff-only || true

cd gpu-worker
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate

# Install dependencies only when requirements changed
REQ_HASH_FILE=.requirements.sha256
REQ_HASH_NOW=$(sha256sum requirements.txt | awk '{print $1}')
REQ_HASH_OLD=""
if [ -f "$REQ_HASH_FILE" ]; then
  REQ_HASH_OLD=$(cat "$REQ_HASH_FILE")
fi
if [ "$REQ_HASH_NOW" != "$REQ_HASH_OLD" ]; then
  pip install --quiet -r requirements.txt
  echo "$REQ_HASH_NOW" > "$REQ_HASH_FILE"
fi

# Optional: flash-attn for maximum speed (fallback to SDPA if build fails)
if pip show flash-attn >/dev/null 2>&1; then
  echo "flash-attn already installed"
else
  pip install flash-attn --no-build-isolation 2>/dev/null || echo "flash-attn install skipped (will use SDPA)"
fi

# .env from passed env vars (vast.ai extra_env) or placeholders
cat > .env << ENV
CPU_API_BASE_URL=${CPU_API_BASE_URL:-https://your-domain.com/api/v1}
GPU_API_KEY=${GPU_API_KEY:-REPLACE_ME}
S3_ENDPOINT_URL=${S3_ENDPOINT_URL:-https://s3-nl.hostkey.com}
S3_ACCESS_KEY=${S3_ACCESS_KEY:-REPLACE_ME}
S3_SECRET_KEY=${S3_SECRET_KEY:-REPLACE_ME}
S3_BUCKET=${S3_BUCKET:-bc4d77ea-clips-ai-s3-storage190904}
WHISPER_MODEL_NAME=openai/whisper-large-v3
WHISPER_DEVICE=cuda
WHISPER_BATCH_SIZE=24
WHISPER_USE_FLASH_ATTN=true
WORKER_ID=vastai-worker-1
WORK_DIR=/tmp/clips_worker
LOG_LEVEL=INFO
ENV

# Preload HuggingFace Whisper model once; skip on subsequent starts
MODEL_READY_MARKER=.model_ready
if [ ! -f "$MODEL_READY_MARKER" ]; then
  python3 -c "
import torch
from transformers import pipeline
from transformers.utils import is_flash_attn_2_available
attn = 'flash_attention_2' if is_flash_attn_2_available() else 'sdpa'
pipe = pipeline('automatic-speech-recognition', model='openai/whisper-large-v3', torch_dtype=torch.float16, device=0, model_kwargs={'attn_implementation': attn})
print('Whisper pipeline loaded OK (attn=%s)' % attn)
" && touch "$MODEL_READY_MARKER" || true
fi

# Start worker only if not running
if pgrep -f "python3 -m worker.main" >/dev/null 2>&1; then
  echo "GPU worker already running"
else
  nohup python3 -m worker.main >> /var/log/gpu-worker.log 2>&1 &
  echo "GPU worker started, PID=$!"
fi


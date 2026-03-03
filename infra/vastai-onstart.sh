#!/bin/bash
# GPU Worker auto-start for Vast.ai (RTX 4000 Ada)
# Env vars CPU_API_BASE_URL, GPU_API_KEY, S3_* are passed via vast.ai extra_env
set -e

export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"

apt-get update -qq
apt-get install -y -qq git python3-pip python3-venv ffmpeg

REPO_URL="${GIT_REPO_URL:-https://github.com/AziCodder/Clips-AI.git}"
cd /root
if [ ! -d "clips" ]; then
  git clone "$REPO_URL" clips
fi
cd clips
git pull

cd gpu-worker
python3 -m venv .venv
source .venv/bin/activate
pip install --quiet -r requirements.txt

# .env from passed env vars (vast.ai extra_env) or placeholders
cat > .env << ENV
CPU_API_BASE_URL=${CPU_API_BASE_URL:-https://your-domain.com/api/v1}
GPU_API_KEY=${GPU_API_KEY:-REPLACE_ME}
S3_ENDPOINT_URL=${S3_ENDPOINT_URL:-https://s3-nl.hostkey.com}
S3_ACCESS_KEY=${S3_ACCESS_KEY:-REPLACE_ME}
S3_SECRET_KEY=${S3_SECRET_KEY:-REPLACE_ME}
S3_BUCKET=${S3_BUCKET:-bc4d77ea-clips-ai-s3-storage190904}
WHISPER_MODEL=large-v3
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16
WORKER_ID=vastai-worker-1
WORK_DIR=/tmp/clips_worker
LOG_LEVEL=INFO
ENV

# Preload WhisperX model (cached for next runs)
python3 -c "
import whisperx
model = whisperx.load_model('large-v3', 'cuda', compute_type='float16')
print('WhisperX large-v3 loaded OK')
" || true

# Start worker
nohup python3 -m worker.main >> /var/log/gpu-worker.log 2>&1 &
echo "GPU worker started, PID=$!"

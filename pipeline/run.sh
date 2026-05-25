#!/usr/bin/env bash
# Wrapper: fija las libs CUDA del venv (cuBLAS/cuDNN) en LD_LIBRARY_PATH
# y lanza el pipeline. Pasa cualquier flag a run_all.py.
#   ./pipeline/run.sh                 # todos los videos
#   ./pipeline/run.sh --only 05-08    # solo los que contengan "05-08"
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv"
NV="$VENV/lib/python3.12/site-packages/nvidia"

export LD_LIBRARY_PATH="$NV/cublas/lib:$NV/cudnn/lib:$NV/cuda_nvrtc/lib:${LD_LIBRARY_PATH:-}"

cd "$ROOT/pipeline"
exec "$VENV/bin/python" run_all.py "$@"

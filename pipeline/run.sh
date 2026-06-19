#!/usr/bin/env bash
# Wrapper: fija las libs CUDA del venv (cuBLAS/cuDNN) en LD_LIBRARY_PATH
# y lanza el pipeline o el servidor web.
#
#   ./pipeline/run.sh                           # pipeline tradicional (todos los videos)
#   ./pipeline/run.sh --only 05-08              # pipeline filtrado
#   ./pipeline/run.sh server                    # servidor web (frontend + API)
#   ./pipeline/run.sh server --port 8080        # servidor en puerto personalizado
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv"
NV="$VENV/lib/python3.12/site-packages/nvidia"

export LD_LIBRARY_PATH="$NV/cublas/lib:$NV/cudnn/lib:$NV/cuda_nvrtc/lib:${LD_LIBRARY_PATH:-}"

cd "$ROOT/pipeline"

if [ "${1:-}" = "server" ]; then
    shift
    PORT="${1:-8000}"
    echo "Iniciando Video Reviewer en http://localhost:${PORT}"
    exec "$VENV/bin/uvicorn" server:app --host 0.0.0.0 --port "$PORT" --reload
else
    exec "$VENV/bin/python" run_all.py "$@"
fi

#!/usr/bin/env bash
# POC Kyutai STT-1B en_fr — live microphone test.
# Terminal 1: ./run-mic-test.sh server
# Terminal 2: ./run-mic-test.sh mic
set -euo pipefail
cd "$(dirname "$0")"

case "${1:-}" in
  server)
    export LD_LIBRARY_PATH="$PWD/cuda-12.8-local/usr/local/cuda-12.8/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    exec ./moshi-server-install/bin/moshi-server worker \
      --config config-stt-en_fr-poc.toml --port 8998
    ;;
  server-cpu)
    export LD_LIBRARY_PATH="$PWD/cuda-12.8-local/usr/local/cuda-12.8/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    exec ./moshi-server-install/bin/moshi-server worker --cpu \
      --config config-stt-en_fr-poc-cpu.toml --port 8998
    ;;
  mic)
    exec uv run delayed-streams-modeling/scripts/stt_from_mic_rust_server.py \
      --url ws://127.0.0.1:8998 --api-key public_token
    ;;
  *)
    echo "usage: $0 server|server-cpu|mic" >&2
    exit 1
    ;;
esac

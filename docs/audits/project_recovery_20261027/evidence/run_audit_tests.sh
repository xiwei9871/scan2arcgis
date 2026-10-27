#!/bin/bash
# Audit reproduction script (Linux). Does not modify repository code.
# Usage: bash run_audit_tests.sh <repo_root> <python_venv>
set -u
ROOT=${1:-.}; PY=${2:-python3}
SHIM=$(mktemp -d)
# backend/core/ml/atomic_store.py imports Windows-only msvcrt; provide a no-op shim for Linux collection.
printf 'LK_NBLCK=2\nLK_UNLCK=0\nLK_LOCK=1\ndef locking(fd, mode, n):\n    return None\n' > "$SHIM/msvcrt.py"
cd "$ROOT"
# matplotlib is required by backend/core/recognition/contour/pipeline.py but missing from requirements.txt
# The full-resolution E2E test hangs >178s on a 4-core/4GB VM, so it is deselected and reported separately.
PYTHONPATH=$SHIM MPLBACKEND=Agg "$PY" -m pytest -q -p no:cacheprovider --tb=line --timeout=90 --timeout-method=thread \
  --deselect backend/tests/api/test_id_contract_e2e.py::test_real_upload_to_recognition_with_original_resolution_geologic_map \
  backend/tests

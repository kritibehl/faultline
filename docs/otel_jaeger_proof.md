# Faultline OTel / Jaeger proof checklist

## Goal
Show the full execution chain in one trace:

submit -> claim -> execute -> complete

## What changed
- Added trace-event emission in `services/worker/worker.py` to write a local JSONL proof file at:
  - `docs/autopsy/assets/otel_trace_chain.jsonl`
- Added a gRPC boundary so the system can demonstrate traceable submit / claim / complete calls across a network interface.

## Demo commands
```bash
export DATABASE_URL='postgresql://faultline:faultline@localhost:5432/faultline'
export OTEL_EXPORTER_OTLP_ENDPOINT='http://localhost:4318'
export OTEL_SERVICE_NAME='faultline'
export FAULTLINE_OTEL_TRACE_LOG='docs/autopsy/assets/otel_trace_chain.jsonl'

python -m services.worker.grpc.server
python -m services.worker.grpc.client
python -m services.worker.worker
```

## Evidence to capture
1. Jaeger screenshot showing one trace containing submit / claim / execute / complete.
2. `docs/autopsy/assets/otel_trace_chain.jsonl` attached in the repo as a machine-readable trace proof.
3. Short README gif or screenshot pair:
   - trace timeline
   - stale-write rejection log

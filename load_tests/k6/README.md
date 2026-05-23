# k6 Inspector API Load Test

This directory contains a k6 load-test script for the Go inspector API.

## Run

Start the inspector:

```bash
cd cmd/faultline-inspector
INSPECTOR_TOKEN=test-token go run .
Run k6:

INSPECTOR_TOKEN=test-token k6 run load_tests/k6/inspector_api_load_test.js
Endpoints covered
/health
/leases
/metrics
Safe claim

This is an endpoint load-test artifact for inspector API validation. It should not be described as production-scale load testing.

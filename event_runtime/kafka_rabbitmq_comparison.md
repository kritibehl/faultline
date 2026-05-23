# Kafka / RabbitMQ / NATS Comparison for Faultline

| System | Best fit | Faultline role |
|---|---|---|
| Kafka | durable ordered event logs | upstream ingestion / replay source |
| RabbitMQ | work queues and routing | async dispatch / retry routing |
| NATS | lightweight pub/sub | low-latency event ingress |

## Design decision

Faultline should not replace a broker. It complements brokers by enforcing stale-worker commit correctness at the database boundary.

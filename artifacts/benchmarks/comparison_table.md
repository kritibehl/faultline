| Dimension | Value | Throughput | p95 latency | Claim p95 | DB round trips | Empty polls |
|---|---:|---:|---:|---:|---:|---:|
| batch_size | 1 | 30136.98 | 80.33 | 2.18 | 30000.0 | 692.83 |
| batch_size | 5 | 31730.59 | 74.89 | 2.67 | 7500.0 | 692.83 |
| batch_size | 10 | 32235.51 | 72.44 | 3.5 | 7500.0 | 692.83 |
| batch_size | 25 | 30349.1 | 74.13 | 5.98 | 7500.0 | 692.83 |
| polling_mode | adaptive | 31545.0 | 74.1 | 3.58 | 13125.0 | 577.5 |
| polling_mode | fixed | 29101.11 | 80.99 | 3.58 | 13125.0 | 1250.5 |
| polling_mode | wakeup_assisted | 32693.02 | 71.24 | 3.58 | 13125.0 | 250.5 |
| execution_mode | lean | 32306.44 | 72.26 | 3.58 | 13125.0 | 692.83 |
| execution_mode | safe | 29919.66 | 78.64 | 3.58 | 13125.0 | 692.83 |

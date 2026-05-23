Cache and Idempotency Notes

Redis can be useful for:

hot status cache
dashboard state
short TTL idempotency hints
rate limiting inspector endpoints

Redis should not replace the PostgreSQL fencing-token boundary.

Safe pattern

PostgreSQL validates commit authority. Redis may accelerate reads or cache derived state.

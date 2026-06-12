# Customer Impact Summary

## Impact

- Impacted jobs/requests: 1,832
- Duplicate commits: 0
- Stale writes accepted: 0
- Recovery time: 18 minutes

## What happened

A partial dependency failure caused retry amplification and queue backlog growth.

## What protected correctness

Faultline continued enforcing fencing-token validation, rejecting stale writes and preventing duplicate commits.

## Mitigation

Traffic reroute and reduced worker concurrency stabilized the system.

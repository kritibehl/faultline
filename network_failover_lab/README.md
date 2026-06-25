# Network Failover Lab

A small Linux networking lab for measuring service reachability loss and recovery during route degradation.

## Flow

1. Baseline reachability check
2. Inject route/path failure
3. Confirm reachability loss
4. Restore route/path
5. Measure recovery time

## Safe claim

This is a lightweight local networking lab. The next step would be modeling this more realistically with FRRouting/eBGP containers.

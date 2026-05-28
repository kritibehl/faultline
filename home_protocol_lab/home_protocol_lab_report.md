
Home Protocol Lab Report
Validated behaviors
Behavior	Proof
device discovered	capability read succeeds
device paired	trust state established
attribute synced	newer epoch accepted
command acknowledged	ack command ID matches issued command
state reconciled	stale controller state rejected
packet loss handled	retry path selected
delayed ack handled	command epoch preserved
duplicate ack handled	acknowledgement deduplicated
reordered command rejected	stale command epoch rejected
hub failover handled	secondary promoted
hub rejoin handled	stale primary write rejected
Reliability takeaway

Home automation reliability depends on controller/accessory state versioning, command acknowledgements, deduplication, reconnect reconciliation, and stale-command rejection.

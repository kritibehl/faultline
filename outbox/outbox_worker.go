package outbox

type OutboxEvent struct {
	EventID        string
	JobID          string
	IdempotencyKey string
	EventType      string
	PayloadJSON    string
	Published      bool
}

type DeliveryResult struct {
	EventsWritten          int
	DuplicatesPrevented    int
	LostEvents             int
	IdempotencyViolations  int
}

func MarkPublished(event OutboxEvent) OutboxEvent {
	event.Published = true
	return event
}

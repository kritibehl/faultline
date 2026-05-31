package outbox

import "crypto/sha256"
import "encoding/hex"

func BuildIdempotencyKey(jobID string, eventType string, payloadHash string) string {
	sum := sha256.Sum256([]byte(jobID + ":" + eventType + ":" + payloadHash))
	return hex.EncodeToString(sum[:])
}

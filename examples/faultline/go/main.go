package main

import (
	"fmt"
	"log"

	"faultline/faultline"
)

func main() {
	client := faultline.NewClient("http://localhost:8000")

	job, err := client.Submit(faultline.SubmitRequest{
		JobPayload:     map[string]any{"task": "email.send", "to": "user@example.com"},
		IdempotencyKey: "email:user@example.com:welcome",
		Queue:          "default",
		TenantID:       "tenant-demo",
	})
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("job=%+v\n", job)

	claim, err := client.Claim(faultline.ClaimRequest{
		WorkerID:  "go-worker-a",
		BatchSize: 1,
		Queue:     "default",
		TenantID:  "tenant-demo",
	})
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("claim=%+v\n", claim)
}

package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"time"

	"github.com/jackc/pgx/v5"
)

type LeaseSummary struct {
	TotalJobs              int `json:"total_jobs"`
	RunningJobs            int `json:"running_jobs"`
	QueuedJobs             int `json:"queued_jobs"`
	FailedJobs             int `json:"failed_jobs"`
	SucceededJobs          int `json:"succeeded_jobs"`
	ExpiredLeases          int `json:"expired_leases"`
	PotentialDuplicateRisk int `json:"potential_duplicate_risk"`
	LeaseRisk              string `json:"lease_risk"`
	SafeToOperate          bool `json:"safe_to_operate"`
}

func getenv(key, fallback string) string {
	v := os.Getenv(key)
	if v == "" {
		return fallback
	}
	return v
}

func connect(ctx context.Context) (*pgx.Conn, error) {
	url := getenv(
		"DATABASE_URL",
		"postgresql://faultline:faultline@localhost:5432/faultline",
	)

	return pgx.Connect(ctx, url)
}

func count(ctx context.Context, conn *pgx.Conn, query string) int {
	var value int

	err := conn.QueryRow(ctx, query).Scan(&value)
	if err != nil {
		return 0
	}

	return value
}

func inspect(ctx context.Context) LeaseSummary {
	conn, err := connect(ctx)
	if err != nil {
		return LeaseSummary{
			LeaseRisk:      "database_unreachable",
			SafeToOperate:  false,
		}
	}
	defer conn.Close(ctx)

	totalJobs := count(ctx, conn,
		`SELECT COUNT(*) FROM jobs`,
	)

	runningJobs := count(ctx, conn,
		`SELECT COUNT(*) FROM jobs WHERE status='running'`,
	)

	queuedJobs := count(ctx, conn,
		`SELECT COUNT(*) FROM jobs WHERE status='queued'`,
	)

	failedJobs := count(ctx, conn,
		`SELECT COUNT(*) FROM jobs WHERE status='failed'`,
	)

	succeededJobs := count(ctx, conn,
		`SELECT COUNT(*) FROM jobs WHERE status='succeeded'`,
	)

	expiredLeases := count(ctx, conn,
		`
		SELECT COUNT(*)
		FROM jobs
		WHERE status='running'
		AND lease_expires_at IS NOT NULL
		AND lease_expires_at < NOW()
		`,
	)

	potentialDuplicateRisk := count(ctx, conn,
		`
		SELECT COUNT(*)
		FROM jobs
		WHERE status='running'
		AND lease_expires_at IS NOT NULL
		AND lease_expires_at < NOW()
		`,
	)

	leaseRisk := "low"
	safe := true

	if expiredLeases > 0 {
		leaseRisk = "medium"
	}

	if potentialDuplicateRisk > 5 {
		leaseRisk = "high"
		safe = false
	}

	return LeaseSummary{
		TotalJobs:              totalJobs,
		RunningJobs:            runningJobs,
		QueuedJobs:             queuedJobs,
		FailedJobs:             failedJobs,
		SucceededJobs:          succeededJobs,
		ExpiredLeases:          expiredLeases,
		PotentialDuplicateRisk: potentialDuplicateRisk,
		LeaseRisk:              leaseRisk,
		SafeToOperate:          safe,
	}
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	result := inspect(ctx)

	status := http.StatusOK
	if !result.SafeToOperate {
		status = http.StatusServiceUnavailable
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)

	_ = json.NewEncoder(w).Encode(result)
}

func metricsHandler(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	result := inspect(ctx)

	w.Header().Set("Content-Type", "text/plain")

	fmt.Fprintf(w,
		"faultline_expired_leases_total %d\n",
		result.ExpiredLeases,
	)

	fmt.Fprintf(w,
		"faultline_duplicate_risk_total %d\n",
		result.PotentialDuplicateRisk,
	)

	if result.SafeToOperate {
		fmt.Fprintf(w, "faultline_safe_to_operate 1\n")
	} else {
		fmt.Fprintf(w, "faultline_safe_to_operate 0\n")
	}
}

func main() {
	http.HandleFunc("/health", healthHandler)
	http.HandleFunc("/metrics", metricsHandler)

	port := getenv("PORT", "8088")

	fmt.Printf("faultline-inspector listening on :%s\n", port)

	err := http.ListenAndServe(":"+port, nil)
	if err != nil {
		panic(err)
	}
}

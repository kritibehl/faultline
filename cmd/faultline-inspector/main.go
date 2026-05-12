package main

import (
	"context"
	"encoding/json"
	"fmt"
	"html/template"
	"net/http"
	"os"
	"time"

	"github.com/jackc/pgx/v5"
)

type LeaseSummary struct {
	TotalJobs              int    `json:"total_jobs"`
	RunningJobs            int    `json:"running_jobs"`
	QueuedJobs             int    `json:"queued_jobs"`
	FailedJobs             int    `json:"failed_jobs"`
	SucceededJobs          int    `json:"succeeded_jobs"`
	ExpiredLeases          int    `json:"expired_leases"`
	PotentialDuplicateRisk int    `json:"potential_duplicate_risk"`
	LeaseRisk              string `json:"lease_risk"`
	SafeToOperate          bool   `json:"safe_to_operate"`
	Mode                   string `json:"mode"`
}

type TraceEvent struct {
	TraceID      string `json:"trace_id"`
	Phase        string `json:"phase"`
	JobID        string `json:"job_id"`
	WorkerID     string `json:"worker_id"`
	LeaseEpoch   int    `json:"lease_epoch"`
	FencingToken int    `json:"fencing_token"`
	Timestamp    string `json:"timestamp"`
}

func getenv(key, fallback string) string {
	v := os.Getenv(key)
	if v == "" {
		return fallback
	}
	return v
}

func connect(ctx context.Context) (*pgx.Conn, error) {
	url := getenv("DATABASE_URL", "")
	if url == "" {
		return nil, fmt.Errorf("DATABASE_URL not set")
	}
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
		return demoSummary("demo_no_database")
	}
	defer conn.Close(ctx)

	totalJobs := count(ctx, conn, `SELECT COUNT(*) FROM jobs`)
	runningJobs := count(ctx, conn, `SELECT COUNT(*) FROM jobs WHERE state='running'`)
	queuedJobs := count(ctx, conn, `SELECT COUNT(*) FROM jobs WHERE state='queued'`)
	failedJobs := count(ctx, conn, `SELECT COUNT(*) FROM jobs WHERE state='failed'`)
	succeededJobs := count(ctx, conn, `SELECT COUNT(*) FROM jobs WHERE state='succeeded'`)

	expiredLeases := count(ctx, conn, `
		SELECT COUNT(*)
		FROM jobs
		WHERE state='running'
		AND lease_expires_at IS NOT NULL
		AND lease_expires_at < NOW()
	`)

	potentialDuplicateRisk := expiredLeases

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
		Mode:                   "postgres",
	}
}

func demoSummary(mode string) LeaseSummary {
	return LeaseSummary{
		TotalJobs:              200,
		RunningJobs:            3,
		QueuedJobs:             0,
		FailedJobs:             0,
		SucceededJobs:          197,
		ExpiredLeases:          1,
		PotentialDuplicateRisk: 1,
		LeaseRisk:              "medium",
		SafeToOperate:          true,
		Mode:                   mode,
	}
}

func sampleTrace() []TraceEvent {
	now := time.Now().UTC()
	return []TraceEvent{
		{"trace-demo-1", "claim_job", "job-1", "worker-a", 1, 1, now.Add(0 * time.Second).Format(time.RFC3339Nano)},
		{"trace-demo-1", "acquire_lease", "job-1", "worker-a", 1, 1, now.Add(1 * time.Second).Format(time.RFC3339Nano)},
		{"trace-demo-1", "lease_takeover", "job-1", "worker-b", 2, 2, now.Add(2 * time.Second).Format(time.RFC3339Nano)},
		{"trace-demo-1", "commit_result", "job-1", "worker-b", 2, 2, now.Add(3 * time.Second).Format(time.RFC3339Nano)},
		{"trace-demo-1", "reject_stale_write", "job-1", "worker-a", 1, 1, now.Add(4 * time.Second).Format(time.RFC3339Nano)},
	}
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	result := inspect(ctx)
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(result)
}

func leasesHandler(w http.ResponseWriter, r *http.Request) {
	healthHandler(w, r)
}

func traceHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{
		"trace": sampleTrace(),
	})
}

func metricsHandler(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	result := inspect(ctx)

	w.Header().Set("Content-Type", "text/plain")
	fmt.Fprintf(w, "faultline_total_jobs %d\n", result.TotalJobs)
	fmt.Fprintf(w, "faultline_running_jobs %d\n", result.RunningJobs)
	fmt.Fprintf(w, "faultline_expired_leases_total %d\n", result.ExpiredLeases)
	fmt.Fprintf(w, "faultline_duplicate_risk_total %d\n", result.PotentialDuplicateRisk)

	if result.SafeToOperate {
		fmt.Fprintf(w, "faultline_safe_to_operate 1\n")
	} else {
		fmt.Fprintf(w, "faultline_safe_to_operate 0\n")
	}
}

func dashboardHandler(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	result := inspect(ctx)

	t := template.Must(template.New("dashboard").Parse(`
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Faultline Inspector</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 40px; background: #f8fafc; color: #111827; }
    .grid { display: grid; grid-template-columns: repeat(3, minmax(160px, 1fr)); gap: 16px; max-width: 900px; }
    .card { background: white; border-radius: 14px; padding: 18px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
    .value { font-size: 32px; font-weight: 700; }
    .safe { color: #047857; }
    .risk { color: #b45309; }
    code { background: #eef2ff; padding: 2px 5px; border-radius: 5px; }
  </style>
</head>
<body>
  <h1>Faultline Inspector</h1>
  <p>Go service for PostgreSQL-backed lease inspection, duplicate-risk summary, and trace export.</p>

  <div class="grid">
    <div class="card"><div>Total Jobs</div><div class="value">{{.TotalJobs}}</div></div>
    <div class="card"><div>Running Jobs</div><div class="value">{{.RunningJobs}}</div></div>
    <div class="card"><div>Expired Leases</div><div class="value">{{.ExpiredLeases}}</div></div>
    <div class="card"><div>Duplicate Risk</div><div class="value">{{.PotentialDuplicateRisk}}</div></div>
    <div class="card"><div>Lease Risk</div><div class="value risk">{{.LeaseRisk}}</div></div>
    <div class="card"><div>Safe To Operate</div><div class="value safe">{{.SafeToOperate}}</div></div>
  </div>

  <h2>Endpoints</h2>
  <ul>
    <li><code>/health</code></li>
    <li><code>/leases</code></li>
    <li><code>/metrics</code></li>
    <li><code>/trace/export</code></li>
  </ul>

  <p>Mode: <code>{{.Mode}}</code></p>
</body>
</html>
`))

	w.Header().Set("Content-Type", "text/html")
	_ = t.Execute(w, result)
}

func main() {
	http.HandleFunc("/", dashboardHandler)
	http.HandleFunc("/health", healthHandler)
	http.HandleFunc("/leases", leasesHandler)
	http.HandleFunc("/metrics", metricsHandler)
	http.HandleFunc("/trace/export", traceHandler)

	port := getenv("PORT", "8088")
	fmt.Printf("faultline-inspector listening on :%s\n", port)

	err := http.ListenAndServe(":"+port, nil)
	if err != nil {
		panic(err)
	}
}

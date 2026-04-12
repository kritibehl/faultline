import json
from pathlib import Path

import matplotlib.pyplot as plt

RESULTS_DIR = Path("benchmarks/results")
OUT_JSON = RESULTS_DIR / "benchmark_data.json"
OUT_PNG = RESULTS_DIR / "faultline_vs_naive.png"

fault_rates = [5, 10, 20]

faultline_rates = []
naive_rates = []

for rate in fault_rates:
    f_path = RESULTS_DIR / f"faultline_fault_{rate}.json"
    n_path = RESULTS_DIR / f"naive_fault_{rate}.json"

    if not f_path.exists():
        raise FileNotFoundError(f"missing {f_path}")
    if not n_path.exists():
        raise FileNotFoundError(f"missing {n_path}")

    f = json.loads(f_path.read_text())
    n = json.loads(n_path.read_text())

    if f["duplicate_commit_rate_percent"] is None:
        raise RuntimeError(f"faultline benchmark failed at fault_pct={rate}")

    faultline_rates.append(float(f["duplicate_commit_rate_percent"]))
    naive_rates.append(float(n["duplicate_commit_rate_percent"]))

payload = {
    "fault_rates_percent": fault_rates,
    "faultline_duplicate_commit_rate_percent": faultline_rates,
    "naive_duplicate_commit_rate_percent": naive_rates,
}

OUT_JSON.write_text(json.dumps(payload, indent=2))

plt.figure(figsize=(8, 5))
plt.plot(fault_rates, faultline_rates, marker="o", label="Faultline (fencing)")
plt.plot(fault_rates, naive_rates, marker="o", label="Naive queue (no fencing)")
plt.xlabel("Injected fault rate (%)")
plt.ylabel("Duplicate commit rate (%)")
plt.title("Duplicate commit rate under fault injection")
plt.legend()
plt.tight_layout()
plt.savefig(OUT_PNG, dpi=160)

print(json.dumps(payload, indent=2))
print(f"wrote {OUT_JSON}")
print(f"wrote {OUT_PNG}")

from sdk.faultline_sdk import ClaimRequest, CompleteRequest, FailRequest, FaultlineClient, WorkerRegistration


def worker_loop() -> None:
    client = FaultlineClient("http://localhost:8000")
    reg = client.register_worker(WorkerRegistration(worker_name="python-worker-a"))
    print(reg)

    claim = client.claim(ClaimRequest(worker_id=reg.worker_id, batch_size=1))
    print("claim:", claim)

    items = claim.get("items", [])
    if not items:
        return

    job = items[0]
    try:
        result = {"status": "ok", "handler": "example"}
        print(client.complete(CompleteRequest(job_id=job["job_id"], fencing_token=int(job["fencing_token"]), result=result)))
    except Exception as e:
        print(client.fail(FailRequest(job_id=job["job_id"], fencing_token=int(job["fencing_token"]), reason=str(e))))


if __name__ == "__main__":
    worker_loop()

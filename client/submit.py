from sdk.faultline_sdk import FaultlineClient, RetryPolicy, SubmitRequest


def submit_example() -> None:
    client = FaultlineClient("http://localhost:8000")
    resp = client.submit(
        SubmitRequest(
            job_payload={"task": "email.send", "to": "user@example.com"},
            idempotency_key="email:user@example.com:welcome",
            retry_policy=RetryPolicy(mode="exponential", max_attempts=5),
        )
    )
    print(resp)


if __name__ == "__main__":
    submit_example()

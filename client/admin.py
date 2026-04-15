from sdk.faultline_sdk import FaultlineClient


def run_reconciliation() -> None:
    client = FaultlineClient("http://localhost:8000")
    print(client.reconcile())


if __name__ == "__main__":
    run_reconciliation()

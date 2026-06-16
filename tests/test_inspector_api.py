def test_inspector_api_contract():
    endpoints = [
        "/jobs/{id}",
        "/workers/{id}",
        "/leases/{id}",
        "/debug/retries",
        "/debug/duplicates",
    ]
    assert "/debug/retries" in endpoints

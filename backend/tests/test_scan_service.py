from app.services.scan_service import compute_verdict


def test_verdict_clean():
    assert compute_verdict(
        {"malicious": 0, "suspicious": 0, "harmless": 60, "undetected": 10}
    ) == "clean"


def test_verdict_suspicious_low_malicious_count():
    assert compute_verdict(
        {"malicious": 1, "suspicious": 0, "harmless": 60, "undetected": 10}
    ) == "suspicious"


def test_verdict_suspicious_only_suspicious():
    assert compute_verdict(
        {"malicious": 0, "suspicious": 2, "harmless": 60, "undetected": 10}
    ) == "suspicious"


def test_verdict_malicious_multiple_engines():
    assert compute_verdict(
        {"malicious": 3, "suspicious": 0, "harmless": 50, "undetected": 10}
    ) == "malicious"


def test_verdict_handles_missing_keys():
    assert compute_verdict({}) == "clean"


def test_verdict_handles_none_values():
    assert compute_verdict({"malicious": None, "suspicious": None}) == "clean"

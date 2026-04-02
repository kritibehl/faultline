from enum import Enum

class FailureClass(str, Enum):
    TIMEOUT = "timeout"
    MALFORMED_OUTPUT = "malformed_output"
    SCHEMA_VIOLATION = "schema_violation"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    PARTIAL_COMPLETION = "partial_completion"
    STALE_COMMIT_REJECTED = "stale_commit_rejected"
    RETRY_STORM = "retry_storm"

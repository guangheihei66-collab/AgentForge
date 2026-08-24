from typing import Literal

HealthState = Literal["HEALTHY", "DEGRADED", "UNHEALTHY", "UNKNOWN"]


def classify_overall(*, backend: HealthState, database: HealthState, provider: HealthState) -> HealthState:
    if backend == "UNHEALTHY" or database == "UNHEALTHY":
        return "UNHEALTHY"
    if backend == "UNKNOWN" or database == "UNKNOWN" or provider == "UNKNOWN":
        return "UNKNOWN"
    if provider != "HEALTHY":
        return "DEGRADED"
    return "HEALTHY"

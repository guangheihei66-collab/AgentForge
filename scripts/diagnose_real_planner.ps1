param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$TaskId = "88cecc62-8721-443f-b91b-89c7f5742d26"
)

$ErrorActionPreference = "Stop"
$planUrl = "$($BaseUrl.TrimEnd('/'))/tasks/$TaskId/plan"
$auditUrl = "$($BaseUrl.TrimEnd('/'))/tasks/$TaskId/audit"

Write-Output "AgentForge safe real-planner diagnostic"
Write-Output "Task: $TaskId"

try {
    $response = Invoke-WebRequest -UseBasicParsing -Method Post -Uri $planUrl `
        -ContentType "application/json" -Body '{"context":{}}'
    Write-Output "Plan request HTTP: $([int]$response.StatusCode)"
} catch [System.Net.WebException] {
    if ($null -ne $_.Exception.Response) {
        $status = $_.Exception.Response.StatusCode.value__
        Write-Output "Plan request HTTP: $status"
    } else {
        Write-Output "Plan request: transport failure"
    }
} catch {
    Write-Output "Plan request: transport failure"
}

try {
    $audit = @(Invoke-RestMethod -Method Get -Uri $auditUrl)
    $failed = $audit | Where-Object { $_.event_type -eq "LLM_PLAN_FAILED" } | Select-Object -Last 1
    if ($null -eq $failed) {
        Write-Output "LLM_PLAN_FAILED event: not found"
        exit 0
    }

    $payload = $failed.payload_summary | ConvertFrom-Json
    $diagnostics = $payload.provider_diagnostics
    Write-Output "Failure category: $($payload.failure_category)"
    Write-Output "Validation stage: $($payload.validation_stage)"
    Write-Output "Attempt count: $($payload.attempt_count)"
    Write-Output "Duration ms: $($payload.duration_ms)"
    Write-Output "Diagnostic fields:"
    foreach ($name in @(
        "upstream_http_status", "finish_reason", "content_present", "content_length",
        "envelope_json_valid", "choices_present", "message_present",
        "content_json_valid", "content_json_object", "reasoning_content_present", "failure_stage"
    )) {
        Write-Output ("  {0}: {1}" -f $name, $diagnostics.$name)
    }
} catch {
    Write-Output "Audit query: unavailable"
}

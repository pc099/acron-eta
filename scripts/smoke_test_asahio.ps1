param(
  [string]$BaseUrl = "https://asahi-production-fa6a.up.railway.app",
  [string]$FrontendUrl = "",
  [string]$ApiKey = "",
  [string]$OrgSlug = "",
  [int]$TimeoutSec = 30,
  [switch]$SkipChat
)

$ErrorActionPreference = "Stop"

function Normalize-Url {
  param([string]$Url)
  if ([string]::IsNullOrWhiteSpace($Url)) { return "" }
  return $Url.Trim().TrimEnd("/")
}

$BaseUrl = Normalize-Url $BaseUrl
$FrontendUrl = Normalize-Url $FrontendUrl

$failures = New-Object System.Collections.Generic.List[string]
$passes = 0

function Write-Pass {
  param([string]$Message)
  $script:passes += 1
  Write-Host "PASS  $Message" -ForegroundColor Green
}

function Write-Fail {
  param([string]$Message)
  $script:failures.Add($Message)
  Write-Host "FAIL  $Message" -ForegroundColor Red
}

function Write-Skip {
  param([string]$Message)
  Write-Host "SKIP  $Message" -ForegroundColor Yellow
}

function Get-Headers {
  param(
    [switch]$UseAuth,
    [hashtable]$Extra = @{},
    [string]$ContentType = "application/json"
  )

  $headers = @{}
  if ($ContentType) {
    $headers["Content-Type"] = $ContentType
  }
  if ($UseAuth -and $ApiKey) {
    $headers["Authorization"] = "Bearer $ApiKey"
  }
  if ($UseAuth -and $OrgSlug) {
    $headers["X-Org-Slug"] = $OrgSlug
  }
  foreach ($key in $Extra.Keys) {
    $headers[$key] = $Extra[$key]
  }
  return $headers
}

function Invoke-RequestSafe {
  param(
    [string]$Method,
    [string]$Url,
    [hashtable]$Headers = @{},
    [string]$Body = ""
  )

  try {
    if ($Method -eq "GET" -or [string]::IsNullOrEmpty($Body)) {
      $response = Invoke-WebRequest -Uri $Url -Method $Method -Headers $Headers -TimeoutSec $TimeoutSec -UseBasicParsing
    } else {
      $response = Invoke-WebRequest -Uri $Url -Method $Method -Headers $Headers -Body $Body -TimeoutSec $TimeoutSec -UseBasicParsing
    }

    $normalizedHeaders = @{}
    foreach ($key in $response.Headers.Keys) {
      $normalizedHeaders[$key.ToString().ToLowerInvariant()] = $response.Headers[$key]
    }

    return [pscustomobject]@{
      Ok = $true
      StatusCode = [int]$response.StatusCode
      Content = [string]$response.Content
      Headers = $normalizedHeaders
      Error = $null
    }
  }
  catch {
    $statusCode = 0
    $content = ""
    $normalizedHeaders = @{}

    if ($_.Exception.Response) {
      $resp = $_.Exception.Response
      try {
        $statusCode = [int]$resp.StatusCode.value__
      } catch {}
      try {
        $stream = $resp.GetResponseStream()
        if ($stream) {
          $reader = New-Object System.IO.StreamReader($stream)
          $content = $reader.ReadToEnd()
          $reader.Close()
        }
      } catch {}
      try {
        foreach ($key in $resp.Headers.Keys) {
          $normalizedHeaders[$key.ToString().ToLowerInvariant()] = $resp.Headers[$key]
        }
      } catch {}
    }

    return [pscustomobject]@{
      Ok = $false
      StatusCode = $statusCode
      Content = $content
      Headers = $normalizedHeaders
      Error = $_.Exception.Message
    }
  }
}

function Parse-JsonSafe {
  param([string]$Text)
  if ([string]::IsNullOrWhiteSpace($Text)) { return $null }
  try {
    return $Text | ConvertFrom-Json
  }
  catch {
    return $null
  }
}

function Require-Status {
  param(
    [string]$Name,
    $Response,
    [int]$ExpectedStatus = 200
  )

  if ($Response.StatusCode -ne $ExpectedStatus) {
    $errorDetail = if ($Response.Error) { $Response.Error } else { $Response.Content }
    Write-Fail "$Name returned HTTP $($Response.StatusCode). $errorDetail"
    return $false
  }

  Write-Pass "$Name returned HTTP $ExpectedStatus"
  return $true
}

Write-Host "Smoke testing backend: $BaseUrl" -ForegroundColor Cyan
if ($FrontendUrl) {
  Write-Host "Frontend origin: $FrontendUrl" -ForegroundColor Cyan
}
if ($ApiKey) {
  Write-Host "Authenticated checks enabled" -ForegroundColor Cyan
}

$health = Invoke-RequestSafe -Method "GET" -Url "$BaseUrl/health" -Headers (Get-Headers -ContentType "")
if (Require-Status -Name "GET /health" -Response $health) {
  $healthJson = Parse-JsonSafe $health.Content
  if ($null -eq $healthJson) {
    Write-Fail "GET /health did not return valid JSON"
  }
  elseif ($healthJson.status -ne "ok") {
    Write-Fail "GET /health returned unexpected status '$($healthJson.status)'"
  }
  else {
    Write-Pass "/health status is ok"
    if ($healthJson.api_docs_enabled -ne $null) {
      Write-Host "INFO  api_docs_enabled=$($healthJson.api_docs_enabled)" -ForegroundColor DarkGray
    }
    if ($healthJson.cors_origins) {
      Write-Host "INFO  cors_origins=$($healthJson.cors_origins -join ', ')" -ForegroundColor DarkGray
    }
    if ($healthJson.cors_origin_regex) {
      Write-Host "INFO  cors_origin_regex=$($healthJson.cors_origin_regex)" -ForegroundColor DarkGray
    }
  }
}

$docs = Invoke-RequestSafe -Method "GET" -Url "$BaseUrl/docs" -Headers (Get-Headers -ContentType "")
if (Require-Status -Name "GET /docs" -Response $docs) {
  if ($docs.Content -match "Swagger UI|swagger-ui") {
    Write-Pass "/docs returned Swagger UI"
  } else {
    Write-Fail "/docs returned HTML but did not look like Swagger UI"
  }
}

$openApi = Invoke-RequestSafe -Method "GET" -Url "$BaseUrl/openapi.json" -Headers (Get-Headers -ContentType "")
if (Require-Status -Name "GET /openapi.json" -Response $openApi) {
  $openApiJson = Parse-JsonSafe $openApi.Content
  if ($null -eq $openApiJson) {
    Write-Fail "/openapi.json did not return valid JSON"
  }
  elseif (-not $openApiJson.openapi) {
    Write-Fail "/openapi.json did not contain an OpenAPI version"
  }
  else {
    Write-Pass "/openapi.json returned a valid OpenAPI document"
  }
}

$plansHeaders = if ($ApiKey) { Get-Headers -UseAuth } else { Get-Headers }
$plans = Invoke-RequestSafe -Method "GET" -Url "$BaseUrl/billing/plans" -Headers $plansHeaders
if ($ApiKey) {
  if (Require-Status -Name "GET /billing/plans" -Response $plans) {
    $plansJson = Parse-JsonSafe $plans.Content
    if ($null -eq $plansJson) {
      Write-Fail "/billing/plans did not return valid JSON"
    }
    elseif ($plansJson.Count -lt 1) {
      Write-Fail "/billing/plans returned an empty plan list"
    }
    else {
      Write-Pass "/billing/plans returned $($plansJson.Count) plan(s)"
    }
  }
}
elseif ($plans.StatusCode -eq 200) {
  Write-Pass "GET /billing/plans returned HTTP 200"
  $plansJson = Parse-JsonSafe $plans.Content
  if ($null -eq $plansJson) {
    Write-Fail "/billing/plans did not return valid JSON"
  }
  elseif ($plansJson.Count -lt 1) {
    Write-Fail "/billing/plans returned an empty plan list"
  }
  else {
    Write-Pass "/billing/plans returned $($plansJson.Count) plan(s)"
  }
}
elseif ($plans.StatusCode -eq 401) {
  Write-Skip "GET /billing/plans requires authentication in this deployment. Pass -ApiKey for billing checks."
}
else {
  Write-Fail "GET /billing/plans returned HTTP $($plans.StatusCode). $($plans.Error)"
}

if ($FrontendUrl) {
  $frontendDocs = Invoke-RequestSafe -Method "GET" -Url "$FrontendUrl/docs" -Headers (Get-Headers -ContentType "")
  if (Require-Status -Name "GET frontend /docs" -Response $frontendDocs) {
    if ($frontendDocs.Content -match "Documentation entry points|API Docs|ASAHIO Docs") {
      Write-Pass "Frontend /docs page loaded"
    } else {
      Write-Fail "Frontend /docs returned HTML but did not match expected content"
    }
  }

  $preflightHeaders = Get-Headers -ContentType ""
  $preflightHeaders["Origin"] = $FrontendUrl
  $preflightHeaders["Access-Control-Request-Method"] = "POST"
  $preflightHeaders["Access-Control-Request-Headers"] = if ($ApiKey) { "authorization,content-type" } else { "content-type" }
  $preflight = Invoke-RequestSafe -Method "OPTIONS" -Url "$BaseUrl/v1/chat/completions" -Headers $preflightHeaders
  if (Require-Status -Name "OPTIONS /v1/chat/completions" -Response $preflight) {
    $allowOrigin = $preflight.Headers["access-control-allow-origin"]
    if ($allowOrigin -eq $FrontendUrl -or $allowOrigin -eq "*") {
      Write-Pass "CORS preflight allows $FrontendUrl"
    } else {
      Write-Fail "CORS preflight allow-origin was '$allowOrigin' instead of '$FrontendUrl'"
    }
  }
}
else {
  Write-Skip "Frontend checks skipped. Pass -FrontendUrl to test docs page and CORS."
}

if ($ApiKey) {
  $subscription = Invoke-RequestSafe -Method "GET" -Url "$BaseUrl/billing/subscription" -Headers (Get-Headers -UseAuth)
  if (Require-Status -Name "GET /billing/subscription" -Response $subscription) {
    $subscriptionJson = Parse-JsonSafe $subscription.Content
    if ($null -eq $subscriptionJson -or -not $subscriptionJson.plan) {
      Write-Fail "/billing/subscription did not return plan data"
    } else {
      Write-Pass "/billing/subscription returned plan '$($subscriptionJson.plan)'"
    }
  }

  $usage = Invoke-RequestSafe -Method "GET" -Url "$BaseUrl/billing/usage" -Headers (Get-Headers -UseAuth)
  if (Require-Status -Name "GET /billing/usage" -Response $usage) {
    $usageJson = Parse-JsonSafe $usage.Content
    if ($null -eq $usageJson -or -not $usageJson.month) {
      Write-Fail "/billing/usage did not return usage data"
    } else {
      Write-Pass "/billing/usage returned current month '$($usageJson.month)'"
    }
  }

  if (-not $SkipChat) {
    $chatBody = @{
      messages = @(
        @{ role = "user"; content = "Reply with the single word healthy." }
      )
      routing_mode = "AUTO"
      intervention_mode = "OBSERVE"
      stream = $false
    } | ConvertTo-Json -Depth 5

    $chat = Invoke-RequestSafe -Method "POST" -Url "$BaseUrl/v1/chat/completions" -Headers (Get-Headers -UseAuth) -Body $chatBody
    if (Require-Status -Name "POST /v1/chat/completions" -Response $chat) {
      $chatJson = Parse-JsonSafe $chat.Content
      if ($null -eq $chatJson) {
        Write-Fail "/v1/chat/completions did not return valid JSON"
      }
      elseif ($null -eq $chatJson.asahio) {
        Write-Fail "/v1/chat/completions response did not include asahio metadata"
      }
      elseif ($null -eq $chatJson.choices -or $chatJson.choices.Count -lt 1) {
        Write-Fail "/v1/chat/completions response did not include choices"
      }
      else {
        Write-Pass "/v1/chat/completions returned ASAHIO metadata and choices"
        Write-Host "INFO  model_used=$($chatJson.asahio.model_used) request_id=$($chatJson.asahio.request_id)" -ForegroundColor DarkGray
      }
    }
  }
  else {
    Write-Skip "Authenticated chat test skipped because -SkipChat was supplied."
  }
}
else {
  Write-Skip "Authenticated checks skipped. Pass -ApiKey to test billing subscription, usage, and chat completions."
}

Write-Host ""
if ($failures.Count -eq 0) {
  Write-Host "Smoke test passed ($passes checks)." -ForegroundColor Green
  exit 0
}

Write-Host "Smoke test failed ($($failures.Count) failure(s), $passes passes)." -ForegroundColor Red
foreach ($failure in $failures) {
  Write-Host " - $failure" -ForegroundColor Red
}
exit 1


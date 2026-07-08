param(
  [string]$Query,
  [string]$QueryFile,
  [string]$BaseUrl = $env:GROK_BASE_URL,
  [string]$Model = $env:GROK_MODEL,
  [int]$MaxTokens = 512,
  [int]$TimeoutSec = 45,
  [string]$OutFile
)

$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom
Add-Type -AssemblyName System.Net.Http

function ConvertTo-AsciiSafeJson {
  param([string]$JsonText)
  $builder = New-Object System.Text.StringBuilder
  foreach ($char in $JsonText.ToCharArray()) {
    $code = [int][char]$char
    if ($code -gt 127) {
      [void]$builder.AppendFormat('\u{0:x4}', $code)
    } else {
      [void]$builder.Append($char)
    }
  }
  return $builder.ToString()
}

if ([string]::IsNullOrWhiteSpace($Query) -and -not [string]::IsNullOrWhiteSpace($QueryFile)) {
  if (-not (Test-Path $QueryFile)) {
    Write-Error "QueryFile does not exist: $QueryFile"
    exit 2
  }
  $Query = [System.IO.File]::ReadAllText($QueryFile, $utf8NoBom)
}

if ([string]::IsNullOrWhiteSpace($Query)) {
  Write-Error "Either Query or QueryFile must be provided."
  exit 2
}

if (-not $BaseUrl -or $BaseUrl.Trim() -eq "") { $BaseUrl = "http://localhost:8317/v1" }
if (-not $Model -or $Model.Trim() -eq "") { $Model = "grok-4.20-reasoning" }
if ($TimeoutSec -le 0) { $TimeoutSec = 45 }

$apiKey = $env:GROK_API_KEY
if (-not $apiKey -or $apiKey.Trim() -eq "") {
  Write-Error "GROK_API_KEY is not set in environment."
  exit 2
}

# Normalize to OpenAI-compatible base URL.
$BaseUrl = $BaseUrl.Trim().TrimEnd('/')
if ($BaseUrl -notmatch '/v1$') { $BaseUrl = "$BaseUrl/v1" }
$uri = "$BaseUrl/chat/completions"

$bodyObj = @{
  model = $Model
  messages = @(
    @{ role = 'user'; content = $Query }
  )
  max_tokens = $MaxTokens
  stream = $false
}

$bodyJson = $bodyObj | ConvertTo-Json -Depth 6

try {
  $client = [System.Net.Http.HttpClient]::new()
  $client.Timeout = [TimeSpan]::FromSeconds($TimeoutSec)
  $request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Post, $uri)
  $request.Headers.Authorization = [System.Net.Http.Headers.AuthenticationHeaderValue]::new('Bearer', $apiKey)
  $request.Content = [System.Net.Http.StringContent]::new($bodyJson, $utf8NoBom, 'application/json')
  $response = $client.SendAsync($request).GetAwaiter().GetResult()
  $responseBytes = $response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
  $json = $utf8NoBom.GetString($responseBytes)
  if (-not $response.IsSuccessStatusCode) {
    throw "HTTP $([int]$response.StatusCode) $($response.ReasonPhrase): $json"
  }
  if (-not [string]::IsNullOrWhiteSpace($OutFile)) {
    [System.IO.File]::WriteAllText($OutFile, $json, $utf8NoBom)
  } else {
    [Console]::Out.Write((ConvertTo-AsciiSafeJson -JsonText $json))
  }
  $request.Dispose()
  $response.Dispose()
  $client.Dispose()
  exit 0
} catch {
  if ($_.Exception -is [System.Threading.Tasks.TaskCanceledException]) {
    Write-Error "Grok request timed out after $TimeoutSec seconds."
  } else {
    Write-Error $_
  }
  exit 1
}

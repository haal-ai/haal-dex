param(
  [string]$Profile = "claude-sso",
  [string]$Region = "us-east-1",
  [int]$Port = 8000
)

aws sso login --profile $Profile
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$pythonExe = $null
$pythonPrefixArgs = @()

# Prefer a non-MSYS2 Windows python.exe (MSYS2 ships its own python.exe and may be earlier on PATH)
try {
  $pythonCandidates = & where.exe python 2>$null
} catch {
  $pythonCandidates = @()
}

foreach ($candidate in $pythonCandidates) {
  if (-not $candidate) { continue }
  if ($candidate -match "\\msys64\\") { continue }
  if ($candidate -match "\\WindowsApps\\python\.exe$") { continue }

  # Only accept an interpreter that can actually import uvicorn
  try {
    & $candidate -c "import uvicorn" 2>$null
    if ($LASTEXITCODE -eq 0) {
      $pythonExe = $candidate
      break
    }
  } catch {
    # ignore
  }
}

if (-not $pythonExe) {
  $pythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
}

$env:AWS_PROFILE = $Profile
$env:AWS_REGION = $Region
$env:AWS_DEFAULT_REGION = $Region
$env:AWS_SDK_LOAD_CONFIG = "1"
$env:INTENT_PIPELINE_STORE_PATH = (Join-Path $PSScriptRoot "backend\pipeline_store.json")

# Configure native DLL lookup for WeasyPrint on Windows (no PATH pollution)
$gtkBin = "C:\\Program Files\\GTK3-Runtime Win64\\bin"
if (Test-Path $gtkBin) {
  $env:INTENT_WEASYPRINT_DLL_DIRS = $gtkBin
}

# Ensure SSO credentials are used (static env creds override profiles if present)
Remove-Item Env:AWS_ACCESS_KEY_ID -ErrorAction SilentlyContinue
Remove-Item Env:AWS_SECRET_ACCESS_KEY -ErrorAction SilentlyContinue
Remove-Item Env:AWS_SESSION_TOKEN -ErrorAction SilentlyContinue
Remove-Item Env:AWS_SECURITY_TOKEN -ErrorAction SilentlyContinue

aws sts get-caller-identity --profile $Profile | Out-Host
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Push-Location (Join-Path $PSScriptRoot "backend")
try {
  if (-not $pythonExe) {
    throw "Python interpreter not found (or none with uvicorn installed). Please install backend Python deps (uvicorn) and ensure a non-MSYS2 python is available."
  }

  & $pythonExe @pythonPrefixArgs -m uvicorn app.main:app --reload --port $Port
} finally {
  Pop-Location
}

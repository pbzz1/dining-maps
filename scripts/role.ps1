# 역할 이름으로 Claude Code 세션을 띄운다. Pixel Agents는 실행 폴더 경로의 마지막 조각을 캐릭터 이름으로 쓰므로,
# dining_maps를 가리키는 정션(바로가기 폴더) roles/<역할>을 만들고 그 안에서 claude를 실행한다.
#   powershell -File scripts/role.ps1 developer            # Claude 개발자 세션
#   powershell -File scripts/role.ps1 intern -Ollama       # Ollama 잡일 사원 (최초 1회: ollama pull qwen3:8b)
param(
  [Parameter(Mandatory)][ValidatePattern('^[a-z][a-z0-9]*$')][string]$Role,  # 하이픈·한글 금지: 경로 조각이 잘린다
  [switch]$Ollama,
  [string]$Model = "qwen3:8b"
)
$repo  = Split-Path $PSScriptRoot -Parent
$roles = Join-Path (Split-Path $repo -Parent) "dining_maps_roles"
$link  = Join-Path $roles $Role
if (-not (Test-Path $roles)) { New-Item -ItemType Directory $roles | Out-Null }
if (-not (Test-Path $link))  { New-Item -ItemType Junction -Path $link -Target $repo | Out-Null }
# Claude Code는 cwd 경로의 영숫자 외 문자를 '-'로 바꿔 ~/.claude/projects/<슬러그>를 만든다. 메모리 폴더를 원본과 공유하도록 정션으로 묶는다.
$slug    = ($link -replace '[^A-Za-z0-9]', '-')
$projDir = Join-Path $env:USERPROFILE ".claude\projects\$slug"
$memSrc  = Join-Path $env:USERPROFILE (".claude\projects\" + ($repo -replace '[^A-Za-z0-9]', '-') + "\memory")
if (-not (Test-Path $projDir)) { New-Item -ItemType Directory $projDir | Out-Null }
if ((Test-Path $memSrc) -and -not (Test-Path (Join-Path $projDir "memory"))) { New-Item -ItemType Junction -Path (Join-Path $projDir "memory") -Target $memSrc | Out-Null }
Set-Location $link

if ($Ollama) {
  $env:ANTHROPIC_BASE_URL = "http://localhost:11434"
  $env:ANTHROPIC_AUTH_TOKEN = "ollama"
  $env:ANTHROPIC_MODEL = $Model
  $role = "너는 dining_maps 프로젝트의 잡일 담당 사원이다. 코드 수정은 하지 않는다. " +
          "하는 일: 로그·테스트 결과 요약, docs/ 문서 오타·링크 점검, 파일 목록 정리, git status 요약. " +
          "답은 항상 5줄 이내. 모르면 모른다고 답한다."
  claude --model $Model --append-system-prompt $role
} else {
  claude
}

# 잡일 사원: Ollama 로컬 모델로 Claude Code를 띄운다. Anthropic 토큰 0원, Pixel Agents에 별도 캐릭터로 표시됨.
# 최초 1회: ollama pull qwen3:8b   (약 5GB, GPU 없는 32GB RAM 노트북에서 CPU로 동작, 느림)
param([string]$Model = "qwen3:8b")
Set-Location (Split-Path $PSScriptRoot -Parent)  # 어디서 실행하든 프로젝트 루트(dining_maps)에서 시작
$env:ANTHROPIC_BASE_URL = "http://localhost:11434"
$env:ANTHROPIC_AUTH_TOKEN = "ollama"
$env:ANTHROPIC_MODEL = $Model
$role = "너는 dining_maps 프로젝트의 잡일 담당 사원이다. 코드 수정은 하지 않는다. " +
        "하는 일: 로그·테스트 결과 요약, docs/ 문서 오타·링크 점검, 파일 목록 정리, git status 요약. " +
        "답은 항상 5줄 이내. 모르면 모른다고 답한다."
claude --model $Model --append-system-prompt $role

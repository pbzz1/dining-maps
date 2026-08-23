# 커밋 + 배포 + push 한 번에.   .\deploy.ps1 "커밋 메시지"   (옵션: --front --back --no-commit)
# deploy.sh를 Git Bash로 실행하는 래퍼. 'bash'만 치면 WSL이 잡혀서 aws/npm을 못 찾는다.
& "C:\Program Files\Git\bin\bash.exe" "$PSScriptRoot\deploy.sh" @args

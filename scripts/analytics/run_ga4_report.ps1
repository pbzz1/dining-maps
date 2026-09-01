# 작업 스케줄러가 매주 실행하는 진입점.
# GA4 리포트를 docs/ga4_report.md 로 갱신한다.
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\Users\taehu\Desktop\취업준비\projects\dining_maps\diningmaps-accessKeys\dining-maps-serviceAccount-506806-a668cdb1c6a3.json"
Set-Location "C:\Users\taehu\Desktop\취업준비\projects\dining_maps"
python scripts\analytics\analyze_ga4_events.py --property-id 449736052

"""요금제 설정. 가격·모델·상한·단가·환율이 전부 여기 있다 -- 코드 다른 곳에 숫자가 흩어지면
"단가가 올랐을 때 어디를 고쳐야 하나"를 못 찾는다.

손해 없음의 산수:
    순매출  = 가격 ÷ 1.1(부가세) × (1 − PG 수수료)
    AI 예산 = 순매출 × BUDGET_RATIO        -- 나머지는 인프라·환율·환불 위험 버퍼
    호출당 최악 비용 = 입력 상한 토큰 × 입력 단가 + max_tokens × 출력 단가   (원화, 환율 고정)
출력은 max_tokens 를 넘을 수 없으니 입력 추정이 상한이면 실제 비용은 항상 최악 비용 이하다.

단가는 Anthropic 1M 토큰당 달러(2026-06 가격표). 환율은 실제보다 높게 고정한다 -- 원화 예산을
달러 비용으로 환산할 때 보수적으로 잡아야 환율이 흔들려도 예산이 실제 비용을 덮는다.
"""
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

# 모든 요금제 공통
PERIOD_DAYS = 30
VAT_RATE = Decimal("0.10")
PG_FEE_RATE = Decimal("0.04")      # 토스 카드 수수료를 보수적으로 4%로 잡는다
BUDGET_RATIO = Decimal("0.5")      # 순매출 중 AI 비용에 쓸 수 있는 몫
USD_KRW = Decimal("1600")          # 1달러 = 1,600원 고정(실제보다 높게)
INPUT_TOKEN_CAP = 8000             # 입력 추정이 이걸 넘으면 호출하지 않는다(대화 기록을 잘라 맞춘다)
# 프롬프트 캐시는 쓰지 않지만 usage 에 나타나면 이 배율로 정산한다(쓰기 1.25배, 읽기 0.1배).
CACHE_WRITE_MULT = Decimal("1.25")
CACHE_READ_MULT = Decimal("0.1")


@dataclass(frozen=True)
class Plan:
    key: str
    label: str
    price_krw: int          # 부가세 포함, 30일 선불
    model: str
    max_tokens: int
    effort: str | None      # Sonnet 5 는 "low", Haiku 4.5 는 effort 를 받지 않으므로 None
    daily_limit: int        # 하루 호출 상한 -- 예산을 하루에 몰아 쓰지 않게
    input_usd_per_mtok: Decimal
    output_usd_per_mtok: Decimal

    @property
    def net_revenue_krw(self) -> Decimal:
        return Decimal(self.price_krw) / (1 + VAT_RATE) * (1 - PG_FEE_RATE)

    @property
    def budget_krw(self) -> Decimal:
        # 버림 -- 예산은 작게 잡는 쪽이 안전하다.
        return (self.net_revenue_krw * BUDGET_RATIO).quantize(Decimal("0.001"), rounding=ROUND_DOWN)


PLANS: dict[str, Plan] = {
    "standard": Plan(
        key="standard", label="Standard", price_krw=3900,
        model="claude-haiku-4-5", max_tokens=1200, effort=None, daily_limit=15,
        input_usd_per_mtok=Decimal("1.00"), output_usd_per_mtok=Decimal("5.00"),
    ),
    "high": Plan(
        key="high", label="High", price_krw=9900,
        model="claude-sonnet-5", max_tokens=2000, effort="low", daily_limit=30,
        input_usd_per_mtok=Decimal("2.00"), output_usd_per_mtok=Decimal("10.00"),
    ),
}

FREE = "free"


def get_plan(key: str) -> Plan:
    if key not in PLANS:
        raise KeyError(f"unknown plan: {key}")
    return PLANS[key]

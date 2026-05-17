# app.py
# Streamlit 낙원계산기 v2 - 4% 룰 보강 버전
# 실행: streamlit run app.py

import math
from typing import Optional, Tuple, List

import pandas as pd
import plotly.express as px
import streamlit as st


# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(
    page_title="낙원계산기",
    page_icon="🌴",
    layout="wide",
)


METHOD_CAPITAL_PRESERVATION = "원금 보존 방식"
METHOD_SAFE_WITHDRAWAL = "4% 룰 방식"


# -----------------------------
# 계산 유틸 함수
# -----------------------------
def pct_to_decimal(value: float) -> float:
    """퍼센트 입력값을 소수로 변환합니다. 예: 2.5 -> 0.025"""
    return float(value) / 100.0


def money_text_manwon(value_manwon: Optional[float]) -> str:
    """만원 단위 숫자를 읽기 쉬운 원화 표현으로 바꿉니다."""
    if value_manwon is None or (isinstance(value_manwon, float) and math.isnan(value_manwon)):
        return "-"

    sign = "-" if value_manwon < 0 else ""
    value = abs(float(value_manwon))

    if value >= 10000:
        return f"{sign}{value / 10000:,.2f}억 원"
    return f"{sign}{value:,.0f}만 원"


def percent_text(value: Optional[float]) -> str:
    """소수 형태의 수익률을 퍼센트 문자열로 바꿉니다. 예: 0.04 -> 4.00%"""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "-"
    return f"{value * 100:,.2f}%"


def growing_annuity_factor(r: float, g: float, n: int) -> float:
    """
    매년 말에 저축하고, 저축액이 매년 g만큼 증가한다고 가정할 때의 미래가치 계수입니다.

    1년차 말 저축액 = A
    2년차 말 저축액 = A * (1+g)
    ...
    n년차 말 저축액 = A * (1+g)^(n-1)
    """
    if n <= 0:
        return 0.0

    if abs(r - g) < 1e-12:
        return n * ((1 + r) ** (n - 1))

    return (((1 + r) ** n) - ((1 + g) ** n)) / (r - g)


def future_value_with_growing_savings(
    current_assets: float,
    annual_saving: float,
    r: float,
    g: float,
    years: int,
) -> float:
    """
    현재자산과 매년 증가하는 저축액을 반영한 은퇴 시점 자산입니다.
    단위는 입력과 동일합니다. 여기서는 만원 단위로 사용합니다.
    """
    if years <= 0:
        # 은퇴까지 남은 기간이 0년이면 현재자산이 곧 은퇴시점 자산입니다.
        return current_assets

    fv_current_assets = current_assets * ((1 + r) ** years)
    fv_savings = annual_saving * growing_annuity_factor(r, g, years)
    return fv_current_assets + fv_savings


def calculate_retirement_spending(
    desired_monthly_spending_today: float,
    inflation: float,
    years_to_retirement: int,
) -> Tuple[float, float]:
    """현재가치 기준 월 생활비를 은퇴 시점 명목 월/연 생활비로 환산합니다."""
    monthly_spending_at_retirement = desired_monthly_spending_today * (
        (1 + inflation) ** max(years_to_retirement, 0)
    )
    annual_spending_at_retirement = monthly_spending_at_retirement * 12
    return monthly_spending_at_retirement, annual_spending_at_retirement


def calculate_target_capital(
    desired_monthly_spending_today: float,
    inflation: float,
    years: int,
    r: float,
    target_method: str,
    safe_withdrawal_rate: float,
) -> Tuple[Optional[float], float, float, Optional[str]]:
    """
    은퇴 시점 목표 낙원금액을 계산합니다.

    주의:
    - 원금 보존 방식: 명목 기대수익률 - 물가상승률만큼만 생활비로 사용한다고 봅니다.
    - 4% 룰 방식: 은퇴 첫해 인출액을 은퇴시점 자산의 일정 비율로 제한한다고 봅니다.
      이후 인출액은 매년 물가상승률만큼 증가시키는 별도 시뮬레이션에서 확인합니다.
    """
    monthly_spending_at_retirement, annual_spending_at_retirement = calculate_retirement_spending(
        desired_monthly_spending_today=desired_monthly_spending_today,
        inflation=inflation,
        years_to_retirement=years,
    )

    if target_method == METHOD_CAPITAL_PRESERVATION:
        real_spread = r - inflation
        if real_spread <= 0:
            return (
                None,
                monthly_spending_at_retirement,
                annual_spending_at_retirement,
                "원금 보존 방식에서는 기대수익률이 인플레이션보다 높아야 목표금액을 계산할 수 있습니다.",
            )
        return (
            annual_spending_at_retirement / real_spread,
            monthly_spending_at_retirement,
            annual_spending_at_retirement,
            None,
        )

    if safe_withdrawal_rate <= 0:
        return (
            None,
            monthly_spending_at_retirement,
            annual_spending_at_retirement,
            "인출률은 0보다 커야 합니다.",
        )

    # 4% 룰의 목표금액은 '첫해 인출액 ÷ 첫해 인출률'입니다.
    # 이 값 자체는 단순하지만, 핵심은 이후 매년 같은 비율을 다시 곱하는 것이 아니라
    # 첫해 인출액을 물가상승률만큼 늘려가며 포트폴리오가 은퇴기간 동안 버티는지 보는 것입니다.
    return (
        annual_spending_at_retirement / safe_withdrawal_rate,
        monthly_spending_at_retirement,
        annual_spending_at_retirement,
        None,
    )


def calculate_sustainable_monthly_spending(
    final_assets: float,
    r: float,
    inflation: float,
    years: int,
    target_method: str,
    safe_withdrawal_rate: float,
) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    """
    은퇴 시점 자산으로 가능한 월 생활비를 계산합니다.

    반환:
    - 은퇴시점 명목 월 생활비
    - 현재가치 월 생활비
    - 경고 메시지

    4% 룰 방식에서는 '매년 남은 자산의 4%'가 아니라
    '은퇴 첫해에 인출 가능한 월 생활비'로 표시합니다.
    """
    if target_method == METHOD_CAPITAL_PRESERVATION:
        real_spread = r - inflation
        if real_spread <= 0:
            return (
                None,
                None,
                "기대수익률이 인플레이션 이하이면 원금 보존 방식의 월 생활비 계산이 어렵습니다.",
            )
        monthly_nominal = final_assets * real_spread / 12
    else:
        if safe_withdrawal_rate <= 0:
            return None, None, "인출률은 0보다 커야 합니다."
        # 4% 룰: 첫해 인출 가능액입니다. 이후에는 물가상승률만큼 금액을 올려가며 시뮬레이션합니다.
        monthly_nominal = final_assets * safe_withdrawal_rate / 12

    discount_factor = (1 + inflation) ** max(years, 0)
    monthly_today_value = monthly_nominal / discount_factor if discount_factor > 0 else monthly_nominal
    return monthly_nominal, monthly_today_value, None


def calculate_required_annual_saving(
    target_capital: Optional[float],
    current_assets: float,
    r: float,
    g: float,
    years: int,
) -> Optional[float]:
    """목표 낙원금액을 달성하기 위해 필요한 첫해 연 저축액을 계산합니다."""
    if target_capital is None:
        return None

    if years <= 0:
        # 기간이 0년이면 저축으로 메울 시간이 없습니다.
        return None

    fv_current_assets = current_assets * ((1 + r) ** years)
    gap = target_capital - fv_current_assets

    if gap <= 0:
        return 0.0

    factor = growing_annuity_factor(r, g, years)
    if factor <= 0:
        return None

    return gap / factor


def solve_required_return_for_goal(
    target_capital: Optional[float],
    current_assets: float,
    annual_saving: float,
    g: float,
    years: int,
    min_rate: float = -0.50,
    max_rate: float = 1.00,
) -> Optional[float]:
    """
    목표 낙원금액 달성에 필요한 기대수익률을 이분 탐색으로 구합니다.
    목표금액이 수익률과 독립적인 4% 룰 방식에서 참고용으로 쓰기 좋습니다.
    """
    if target_capital is None or years <= 0:
        return None

    def f(rate: float) -> float:
        return future_value_with_growing_savings(
            current_assets=current_assets,
            annual_saving=annual_saving,
            r=rate,
            g=g,
            years=years,
        ) - target_capital

    low = min_rate
    high = max_rate

    # 낮은 수익률에서도 이미 목표 달성이면 낮은 값 반환
    if f(low) >= 0:
        return low

    # 높은 수익률에서도 목표 미달이면 계산 불가
    if f(high) < 0:
        return None

    for _ in range(100):
        mid = (low + high) / 2
        if f(mid) >= 0:
            high = mid
        else:
            low = mid

    return high


def make_projection_table(
    current_assets: float,
    annual_saving: float,
    r: float,
    g: float,
    years: int,
    desired_monthly_spending_today: float,
    inflation: float,
    target_method: str,
    safe_withdrawal_rate: float,
) -> pd.DataFrame:
    """은퇴 전 연도별 자산 추이와 목표 낙원금액 추이를 표로 만듭니다."""
    rows = []
    asset = current_assets
    saving = annual_saving

    for year in range(0, years + 1):
        future_monthly_spending = desired_monthly_spending_today * ((1 + inflation) ** year)
        future_annual_spending = future_monthly_spending * 12

        target_capital = None
        if target_method == METHOD_CAPITAL_PRESERVATION:
            real_spread = r - inflation
            if real_spread > 0:
                target_capital = future_annual_spending / real_spread
        else:
            if safe_withdrawal_rate > 0:
                target_capital = future_annual_spending / safe_withdrawal_rate

        rows.append(
            {
                "연도": year,
                "예상자산(만원)": asset,
                "희망 월생활비_미래가치(만원)": future_monthly_spending,
                "목표 낙원금액(만원)": target_capital,
            }
        )

        if year < years:
            # 매년 말에 저축한다고 가정합니다.
            asset = asset * (1 + r) + saving
            saving = saving * (1 + g)

    return pd.DataFrame(rows)


def simulate_retirement_withdrawals(
    initial_assets: float,
    first_year_annual_spending: float,
    inflation: float,
    retirement_years: int,
    annual_return: float,
    returns_by_year: Optional[List[float]] = None,
) -> Tuple[pd.DataFrame, Optional[int]]:
    """
    은퇴 후 인출 시뮬레이션입니다.

    4% 룰의 핵심을 반영합니다.
    - 첫해 인출액: 은퇴 첫해 필요한 연 생활비
    - 다음 해부터: 전년도 인출액을 물가상승률만큼 증가
    - 포트폴리오: 주식/채권 혼합 포트폴리오의 연 수익률 가정으로 성장

    단순화를 위해 매년 초 인출 후 남은 자산이 연간 수익률로 성장한다고 가정합니다.
    """
    rows = []
    asset = initial_assets
    withdrawal = first_year_annual_spending
    failed_year = None

    for year in range(1, retirement_years + 1):
        start_asset = asset
        year_return = annual_return
        if returns_by_year is not None and year <= len(returns_by_year):
            year_return = returns_by_year[year - 1]

        # 매년 초 인출한다고 가정합니다. 보수적인 가정입니다.
        asset_after_withdrawal = start_asset - withdrawal

        if asset_after_withdrawal < 0:
            rows.append(
                {
                    "은퇴 후 경과연수": year,
                    "연초자산(만원)": start_asset,
                    "연 인출액(만원)": withdrawal,
                    "인출 후 자산(만원)": max(asset_after_withdrawal, 0),
                    "적용 수익률": year_return,
                    "투자수익(만원)": 0.0,
                    "연말자산(만원)": 0.0,
                    "잔존 여부": "고갈",
                }
            )
            failed_year = year
            break

        investment_gain = asset_after_withdrawal * year_return
        end_asset = asset_after_withdrawal + investment_gain

        rows.append(
            {
                "은퇴 후 경과연수": year,
                "연초자산(만원)": start_asset,
                "연 인출액(만원)": withdrawal,
                "인출 후 자산(만원)": asset_after_withdrawal,
                "적용 수익률": year_return,
                "투자수익(만원)": investment_gain,
                "연말자산(만원)": end_asset,
                "잔존 여부": "잔존" if end_asset > 0 else "고갈",
            }
        )

        asset = max(end_asset, 0)
        withdrawal = withdrawal * (1 + inflation)

    return pd.DataFrame(rows), failed_year


def build_sequence_risk_returns(
    base_return: float,
    retirement_years: int,
    first_year_shock: float = -0.20,
    second_year_shock: float = -0.10,
) -> List[float]:
    """은퇴 직후 하락장 스트레스 테스트용 수익률 배열을 만듭니다."""
    if retirement_years <= 0:
        return []
    if retirement_years == 1:
        return [first_year_shock]
    return [first_year_shock, second_year_shock] + [base_return] * max(retirement_years - 2, 0)


def format_simulation_table(df: pd.DataFrame) -> pd.DataFrame:
    """은퇴 후 인출표를 화면 표시용 문자열로 변환합니다."""
    display_df = df.copy()
    money_cols = [
        "연초자산(만원)",
        "연 인출액(만원)",
        "인출 후 자산(만원)",
        "투자수익(만원)",
        "연말자산(만원)",
    ]
    for col in money_cols:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(money_text_manwon)
    if "적용 수익률" in display_df.columns:
        display_df["적용 수익률"] = display_df["적용 수익률"].apply(percent_text)
    return display_df


# -----------------------------
# 화면 구성
# -----------------------------
st.title("🌴 낙원계산기")
st.caption(
    "현재자산, 연 저축액, 기대수익률, 은퇴까지 남은 시간을 넣어 "
    "은퇴 시점 자산과 가능한 월 생활비를 계산합니다."
)

with st.sidebar:
    st.header("입력값")

    st.subheader("1) 현재 상황")
    current_assets = st.number_input(
        "현재 보유자산",
        min_value=0.0,
        value=5000.0,
        step=100.0,
        format="%.0f",
        help="만원 단위입니다. 예: 5,000만 원이면 5000",
    )
    annual_saving = st.number_input(
        "연 저축/투자 가능액",
        min_value=0.0,
        value=1800.0,
        step=100.0,
        format="%.0f",
        help="만원 단위입니다. 월 150만 원이면 연 1,800만 원",
    )
    years_to_retirement = st.number_input(
        "은퇴까지 남은 기간",
        min_value=0,
        max_value=80,
        value=30,
        step=1,
        help="0년 입력도 가능합니다. 0년이면 현재자산을 은퇴시점 자산으로 계산합니다.",
    )

    st.subheader("2) 수익률과 물가")
    expected_return_pct = st.number_input(
        "은퇴 전 명목 기대수익률(%)",
        min_value=-50.0,
        max_value=100.0,
        value=7.0,
        step=0.1,
        format="%.2f",
        help="소수점 입력 가능. 예: 7 또는 7.5",
    )
    savings_growth_pct = st.number_input(
        "저축증가율 / 인플레이션(%)",
        min_value=-20.0,
        max_value=50.0,
        value=2.5,
        step=0.1,
        format="%.2f",
        help="소수점 입력 가능. 예: 2.5",
    )

    use_same_inflation = st.checkbox(
        "생활비 물가상승률도 위 값과 같게 사용",
        value=True,
    )

    if use_same_inflation:
        living_inflation_pct = savings_growth_pct
    else:
        living_inflation_pct = st.number_input(
            "생활비 물가상승률(%)",
            min_value=-20.0,
            max_value=50.0,
            value=2.5,
            step=0.1,
            format="%.2f",
        )

    st.subheader("3) 원하는 생활비")
    desired_monthly_spending_today = st.number_input(
        "희망 월 생활비: 현재가치",
        min_value=0.0,
        value=300.0,
        step=10.0,
        format="%.0f",
        help="만원 단위입니다. 현재 돈 가치 기준으로 입력합니다.",
    )

    target_method = st.radio(
        "목표 낙원금액 계산 방식",
        options=[METHOD_CAPITAL_PRESERVATION, METHOD_SAFE_WITHDRAWAL],
        index=0,
        help=(
            "원금 보존 방식: 은퇴 시점 생활비를 기대수익률-물가상승률로 나눕니다. "
            "4% 룰 방식: 은퇴 첫해 인출액을 기준으로 필요자산을 계산하고, "
            "은퇴 후에는 인출액을 매년 물가만큼 올려가며 30년 생존 여부를 시뮬레이션합니다."
        ),
    )

    if target_method == METHOD_SAFE_WITHDRAWAL:
        safe_withdrawal_rate_pct = st.number_input(
            "첫해 인출률(%)",
            min_value=0.1,
            max_value=20.0,
            value=4.0,
            step=0.1,
            format="%.2f",
            help="4% 룰에서 말하는 인출률은 보통 은퇴 첫해 인출률입니다. 이후에는 금액을 물가상승률만큼 올린다고 봅니다.",
        )

        retirement_years_after = st.number_input(
            "은퇴 후 인출 기간(년)",
            min_value=1,
            max_value=80,
            value=30,
            step=1,
            help="4% 룰은 보통 30년 인출기간을 기준으로 많이 설명됩니다.",
        )

        with st.expander("은퇴 후 주식/채권 혼합 포트폴리오 가정", expanded=False):
            stock_weight_pct = st.slider(
                "은퇴 후 주식 비중(%)",
                min_value=0,
                max_value=100,
                value=60,
                step=5,
            )
            bond_weight_pct = 100 - stock_weight_pct
            stock_return_pct = st.number_input(
                "은퇴 후 주식 기대수익률(%)",
                min_value=-50.0,
                max_value=100.0,
                value=7.0,
                step=0.1,
                format="%.2f",
            )
            bond_return_pct = st.number_input(
                "은퇴 후 채권 기대수익률(%)",
                min_value=-50.0,
                max_value=100.0,
                value=3.0,
                step=0.1,
                format="%.2f",
            )
            sequence_risk_test = st.checkbox(
                "은퇴 직후 하락장 스트레스 테스트도 보기",
                value=True,
                help="단순 예시입니다. 은퇴 1년차 -20%, 2년차 -10%, 이후 기본 수익률로 가정합니다.",
            )
    else:
        safe_withdrawal_rate_pct = 4.0
        retirement_years_after = 30
        stock_weight_pct = 60
        bond_weight_pct = 40
        stock_return_pct = expected_return_pct
        bond_return_pct = max(living_inflation_pct, 2.0)
        sequence_risk_test = False

    st.divider()
    show_projection_table = st.checkbox("은퇴 전 연도별 상세표 보기", value=False)
    show_retirement_table = st.checkbox("은퇴 후 인출 상세표 보기", value=False)


# 퍼센트 → 소수
r = pct_to_decimal(expected_return_pct)
g = pct_to_decimal(savings_growth_pct)
inflation = pct_to_decimal(living_inflation_pct)
safe_withdrawal_rate = pct_to_decimal(safe_withdrawal_rate_pct)
n = int(years_to_retirement)
retirement_years_after = int(retirement_years_after)
stock_weight = pct_to_decimal(stock_weight_pct)
bond_weight = pct_to_decimal(bond_weight_pct)
stock_return = pct_to_decimal(stock_return_pct)
bond_return = pct_to_decimal(bond_return_pct)
post_retirement_return = stock_weight * stock_return + bond_weight * bond_return

# 핵심 계산
final_assets = future_value_with_growing_savings(
    current_assets=current_assets,
    annual_saving=annual_saving,
    r=r,
    g=g,
    years=n,
)

target_capital, monthly_spending_at_retirement, annual_spending_at_retirement, target_warning = calculate_target_capital(
    desired_monthly_spending_today=desired_monthly_spending_today,
    inflation=inflation,
    years=n,
    r=r,
    target_method=target_method,
    safe_withdrawal_rate=safe_withdrawal_rate,
)

monthly_nominal, monthly_today_value, spending_warning = calculate_sustainable_monthly_spending(
    final_assets=final_assets,
    r=r,
    inflation=inflation,
    years=n,
    target_method=target_method,
    safe_withdrawal_rate=safe_withdrawal_rate,
)

required_annual_saving = calculate_required_annual_saving(
    target_capital=target_capital,
    current_assets=current_assets,
    r=r,
    g=g,
    years=n,
)

required_return_for_goal = None
if target_method == METHOD_SAFE_WITHDRAWAL:
    required_return_for_goal = solve_required_return_for_goal(
        target_capital=target_capital,
        current_assets=current_assets,
        annual_saving=annual_saving,
        g=g,
        years=n,
    )

shortage = None if target_capital is None else final_assets - target_capital


# -----------------------------
# 결과 카드
# -----------------------------
st.subheader("📌 계산 결과")

if n == 0:
    st.info("은퇴까지 남은 기간이 0년입니다. 현재 보유자산을 그대로 은퇴시점 자산으로 계산했습니다.")

if target_warning:
    st.warning(target_warning)

if spending_warning:
    st.warning(spending_warning)

if target_method == METHOD_SAFE_WITHDRAWAL:
    st.info(
        "4% 룰은 '매년 남은 자산의 4%를 계속 인출'한다는 뜻이 아니라, "
        "은퇴 첫해에 초기 은퇴자산의 4%를 인출하고 이후 인출액을 물가상승률만큼 올려가며 "
        "주식·채권 혼합 포트폴리오가 일정 기간 버티는지를 보는 개념에 가깝습니다."
    )

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("은퇴 시점 예상자산", money_text_manwon(final_assets))
    st.caption("현재자산 + 연 저축액 + 복리수익률 + 저축증가율 반영")

with col2:
    st.metric("은퇴 시점 희망 월 생활비", money_text_manwon(monthly_spending_at_retirement))
    st.caption("현재가치 월 생활비에 물가상승률 반영")

with col3:
    st.metric("목표 낙원금액", money_text_manwon(target_capital))
    st.caption(target_method)

col4, col5, col6 = st.columns(3)

with col4:
    label = "가능 월 생활비: 은퇴 첫해" if target_method == METHOD_SAFE_WITHDRAWAL else "가능 월 생활비: 은퇴시점 금액"
    st.metric(label, money_text_manwon(monthly_nominal))
    st.caption("은퇴 시점 명목금액 기준")

with col5:
    label = "첫해 가능 월 생활비: 현재가치" if target_method == METHOD_SAFE_WITHDRAWAL else "가능 월 생활비: 현재가치"
    st.metric(label, money_text_manwon(monthly_today_value))
    st.caption("오늘 돈 가치로 환산")

with col6:
    if shortage is None:
        st.metric("목표 대비 초과/부족", "-")
    else:
        st.metric("목표 대비 초과/부족", money_text_manwon(shortage))
        if shortage >= 0:
            st.caption("목표 낙원금액 달성 가능")
        else:
            st.caption("현재 입력값 기준 목표까지 부족")


# -----------------------------
# 추가 진단
# -----------------------------
st.subheader("🧭 목표 달성을 위한 참고값")

col7, col8, col9 = st.columns(3)

with col7:
    if n <= 0:
        if target_capital is not None:
            instant_gap = max(target_capital - current_assets, 0)
            st.metric("즉시 추가로 필요한 금액", money_text_manwon(instant_gap))
            st.caption("남은 기간이 0년이라 저축기간 없이 바로 필요한 부족액입니다.")
        else:
            st.metric("필요 연 저축액", "-")
    else:
        st.metric("필요 첫해 연 저축액", money_text_manwon(required_annual_saving))
        st.caption("이후 매년 저축증가율만큼 저축액이 늘어난다고 가정")

with col8:
    if required_annual_saving is not None:
        st.metric("필요 첫해 월 저축액", money_text_manwon(required_annual_saving / 12))
    else:
        st.metric("필요 첫해 월 저축액", "-")
    st.caption("목표금액 기준 역산")

with col9:
    if target_method == METHOD_SAFE_WITHDRAWAL:
        st.metric("목표 달성 필요 기대수익률", percent_text(required_return_for_goal))
        st.caption("현재 저축액과 기간을 고정한 참고값")
    else:
        st.metric("실질 수익률 차이", percent_text(r - inflation))
        st.caption("명목 기대수익률 - 생활비 물가상승률")


# -----------------------------
# 은퇴 후 4% 룰 시뮬레이션
# -----------------------------
if target_method == METHOD_SAFE_WITHDRAWAL:
    st.subheader("🏖️ 은퇴 후 4% 룰 인출 시뮬레이션")

    sim_df, failed_year = simulate_retirement_withdrawals(
        initial_assets=final_assets,
        first_year_annual_spending=annual_spending_at_retirement,
        inflation=inflation,
        retirement_years=retirement_years_after,
        annual_return=post_retirement_return,
    )

    final_balance = 0.0 if sim_df.empty else float(sim_df.iloc[-1]["연말자산(만원)"])
    success = failed_year is None and len(sim_df) == retirement_years_after and final_balance > 0

    col10, col11, col12 = st.columns(3)
    with col10:
        st.metric("은퇴 후 포트폴리오 기대수익률", percent_text(post_retirement_return))
        st.caption(f"주식 {stock_weight_pct}% / 채권 {bond_weight_pct}% 가정")
    with col11:
        st.metric("기본 시나리오 결과", "성공" if success else "고갈")
        if failed_year:
            st.caption(f"은퇴 후 {failed_year}년 차에 자산 고갈")
        else:
            st.caption(f"{retirement_years_after}년 인출 후 잔액 {money_text_manwon(final_balance)}")
    with col12:
        first_year_withdrawable = final_assets * safe_withdrawal_rate
        st.metric("첫해 4% 기준 인출 가능액", money_text_manwon(first_year_withdrawable))
        st.caption(f"희망 첫해 연 생활비 {money_text_manwon(annual_spending_at_retirement)}")

    if annual_spending_at_retirement > final_assets * safe_withdrawal_rate:
        st.warning(
            "희망 생활비가 첫해 인출률 기준 가능액보다 큽니다. "
            "즉, 계산기상으로는 4% 룰 목표금액보다 은퇴시점 예상자산이 부족한 상태입니다."
        )
    else:
        st.success(
            "희망 생활비가 첫해 인출률 기준 가능액 이내입니다. "
            "다만 실제 은퇴 후에는 수익률 순서, 세금, 건강보험료, 지출 변화가 중요합니다."
        )

    sim_chart_df = sim_df.melt(
        id_vars="은퇴 후 경과연수",
        value_vars=["연말자산(만원)", "연 인출액(만원)"],
        var_name="구분",
        value_name="금액(만원)",
    )
    fig_sim = px.line(
        sim_chart_df,
        x="은퇴 후 경과연수",
        y="금액(만원)",
        color="구분",
        markers=True,
        title="은퇴 후 자산 잔액과 연 인출액",
    )
    fig_sim.update_layout(
        yaxis_title="금액(만원)",
        xaxis_title="은퇴 후 경과연수",
        legend_title_text="",
    )
    st.plotly_chart(fig_sim, use_container_width=True)

    if sequence_risk_test:
        stress_returns = build_sequence_risk_returns(
            base_return=post_retirement_return,
            retirement_years=retirement_years_after,
        )
        stress_df, stress_failed_year = simulate_retirement_withdrawals(
            initial_assets=final_assets,
            first_year_annual_spending=annual_spending_at_retirement,
            inflation=inflation,
            retirement_years=retirement_years_after,
            annual_return=post_retirement_return,
            returns_by_year=stress_returns,
        )
        stress_final_balance = 0.0 if stress_df.empty else float(stress_df.iloc[-1]["연말자산(만원)"])
        stress_success = stress_failed_year is None and len(stress_df) == retirement_years_after and stress_final_balance > 0

        with st.expander("은퇴 직후 하락장 스트레스 테스트", expanded=True):
            st.write(
                "은퇴 1년 차 -20%, 2년 차 -10%, 이후 기본 포트폴리오 기대수익률로 회복한다고 가정한 단순 테스트입니다. "
                "4% 룰에서 특히 중요한 '수익률 순서 위험'을 체감하기 위한 교육용 시나리오입니다."
            )
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                st.metric("스트레스 시나리오 결과", "성공" if stress_success else "고갈")
                if stress_failed_year:
                    st.caption(f"은퇴 후 {stress_failed_year}년 차에 자산 고갈")
                else:
                    st.caption(f"{retirement_years_after}년 인출 후 잔액 {money_text_manwon(stress_final_balance)}")
            with col_s2:
                st.metric("기본 대비 잔액 차이", money_text_manwon(stress_final_balance - final_balance))
                st.caption("은퇴 직후 하락장이 장기 잔액에 주는 영향")

            stress_chart_df = stress_df.melt(
                id_vars="은퇴 후 경과연수",
                value_vars=["연말자산(만원)", "연 인출액(만원)"],
                var_name="구분",
                value_name="금액(만원)",
            )
            fig_stress = px.line(
                stress_chart_df,
                x="은퇴 후 경과연수",
                y="금액(만원)",
                color="구분",
                markers=True,
                title="스트레스 시나리오: 자산 잔액과 연 인출액",
            )
            fig_stress.update_layout(
                yaxis_title="금액(만원)",
                xaxis_title="은퇴 후 경과연수",
                legend_title_text="",
            )
            st.plotly_chart(fig_stress, use_container_width=True)

    if show_retirement_table:
        st.write("은퇴 후 인출 상세표")
        st.dataframe(format_simulation_table(sim_df), use_container_width=True)


# -----------------------------
# 은퇴 전 그래프
# -----------------------------
st.subheader("📈 은퇴 전 연도별 예상 추이")

projection = make_projection_table(
    current_assets=current_assets,
    annual_saving=annual_saving,
    r=r,
    g=g,
    years=n,
    desired_monthly_spending_today=desired_monthly_spending_today,
    inflation=inflation,
    target_method=target_method,
    safe_withdrawal_rate=safe_withdrawal_rate,
)

chart_df = projection.melt(
    id_vars="연도",
    value_vars=["예상자산(만원)", "목표 낙원금액(만원)"],
    var_name="구분",
    value_name="금액(만원)",
).dropna()

if chart_df.empty:
    st.write("그래프로 표시할 값이 없습니다.")
else:
    fig = px.line(
        chart_df,
        x="연도",
        y="금액(만원)",
        color="구분",
        markers=True,
        title="예상자산 vs 목표 낙원금액",
    )
    fig.update_layout(
        yaxis_title="금액(만원)",
        xaxis_title="은퇴까지 경과 연수",
        legend_title_text="",
    )
    st.plotly_chart(fig, use_container_width=True)

if show_projection_table:
    display_df = projection.copy()
    for col in ["예상자산(만원)", "희망 월생활비_미래가치(만원)", "목표 낙원금액(만원)"]:
        display_df[col] = display_df[col].apply(money_text_manwon)
    st.dataframe(display_df, use_container_width=True)


# -----------------------------
# 계산 기준 설명
# -----------------------------
with st.expander("계산 기준 / 공식 보기"):
    st.markdown(
        """
### 1) 은퇴 시점 예상자산

현재자산은 은퇴 시점까지 복리로 증가하고, 매년 말 저축액을 추가로 넣는다고 가정했습니다.

```text
은퇴시점 예상자산
= 현재자산 × (1 + 기대수익률)^기간
+ 연저축액 × 증가저축 미래가치계수
```

### 2) 원금 보존 방식의 목표 낙원금액

원금은 되도록 건드리지 않고, 실질수익률만으로 생활비를 만든다고 보는 방식입니다.

```text
목표 낙원금액
= 은퇴시점 연 생활비 ÷ (명목 기대수익률 - 생활비 물가상승률)
```

예를 들어 명목 기대수익률 7%, 물가상승률 2.5%라면  
생활비를 만들어내는 실질 수익률 차이는 4.5%로 봅니다.

### 3) 4% 룰 방식의 목표 낙원금액

4% 룰은 단순히 매년 남은 자산의 4%를 다시 계산해서 쓰는 방식이 아닙니다.

```text
첫해 인출 가능액 = 은퇴시점 초기자산 × 첫해 인출률
목표 낙원금액 = 은퇴시점 첫해 연 생활비 ÷ 첫해 인출률
```

그다음 해부터는 보통 아래처럼 봅니다.

```text
2년차 인출액 = 1년차 인출액 × (1 + 물가상승률)
3년차 인출액 = 2년차 인출액 × (1 + 물가상승률)
...
```

즉 4% 룰의 핵심은 **첫해 4% + 이후 물가연동 인출 + 주식/채권 혼합 포트폴리오의 30년 지속 가능성**입니다.

### 4) 주의

이 계산기는 교육용 시뮬레이터입니다.  
실제 트리니티 연구나 벤젠 연구처럼 과거 모든 주식·채권 수익률 구간을 재현한 백테스트는 아닙니다.  
세금, 건강보험료, 공적연금, 사적연금, 환율, 실제 생활비 변화, 투자 수익률 순서 위험은 단순화했습니다.
"""
    )

st.divider()
st.caption("※ 투자 권유가 아닌 교육용 계산기입니다. 입력값을 바꿔가며 ‘내 숫자’를 확인하는 용도로 사용하세요.")

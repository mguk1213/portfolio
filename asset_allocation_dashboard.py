import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_datareader.data as web
import plotly.express as px
from datetime import datetime, timedelta
import google.generativeai as genai
from duckduckgo_search import DDGS

# -----------------------------------------------------------------------------
# 1. 페이지 설정 및 스타일
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="나만의 자산배분 대시보드",
    page_icon="📈",
    layout="wide"
)

# 커스텀 CSS
st.markdown("""
    <style>
    .big-font {
        font-size: 50px !important;
        font-weight: bold;
        text-align: center;
        padding: 20px;
        border-radius: 10px;
        margin-bottom: 20px;
    }
    .metric-container {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
        text-align: center;
    }
    .ai-box {
        background-color: #e8f0fe;
        border-left: 5px solid #4285f4;
        padding: 20px;
        border-radius: 5px;
        margin-top: 10px;
    }
    .source-link {
        font-size: 0.8em;
        color: #666;
        text-decoration: none;
        margin-right: 10px;
    }
    </style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. 데이터 가져오기 함수 (캐싱 적용)
# -----------------------------------------------------------------------------
@st.cache_data(ttl=3600)
def get_latest_news():
    news_text = ""
    try:
        # 1. 나스닥(QQQ)과 하이일드(HYG) 관련 뉴스 가져오기
        tickers = ["QQQ", "HYG"]
        for ticker in tickers:
            stock = yf.Ticker(ticker)
            news_list = stock.news
            
            # 최신 뉴스 3개씩만 가져오기
            for news in news_list[:3]:
                title = news.get('title', '')
                # yfinance 뉴스는 본문 전체가 없을 때가 많아 제목으로 승부
                news_text += f"- [{ticker}] {title}\n"
                
    except Exception as e:
        news_text = f"뉴스 수집 중 오류 발생: {e}"
        
    return news_text

# -----------------------------------------------------------------------------
# 3. 시장 상태 판단 로직
# -----------------------------------------------------------------------------
def determine_market_regime(price, ma200, spread):
    if spread < 3.5 and price > ma200:
        return "평온기 (Risk On)", "green", "#d4edda", "#155724"
    elif spread > 5.0 and price < ma200:
        return "공포기 (Risk Off)", "red", "#f8d7da", "#721c24"
    else:
        return "경계기 (Neutral/Caution)", "orange", "#fff3cd", "#856404"

# -----------------------------------------------------------------------------
# 4. 포트폴리오 비중 정의
# -----------------------------------------------------------------------------
def get_portfolio_weights(regime_code):
    tickers = ['QQQ', 'ITA', 'EMXC', 'SHYG', 'TLT', 'GLD', 'BIL']
    
    if "평온기" in regime_code:
        weights = [40, 0, 20, 40, 0, 0, 0]
        desc = ['나스닥 100', '미국 방산', '이머징마켓(중국제외)', '하이일드 채권', '미국 장기채', '금', '초단기채(현금)']
    elif "공포기" in regime_code:
        weights = [0, 0, 0, 0, 50, 20, 30]
        desc = ['나스닥 100', '미국 방산', '이머징마켓(중국제외)', '하이일드 채권', '미국 장기채', '금', '초단기채(현금)']
    else: # 경계기
        weights = [20, 10, 0, 30, 20, 20, 0]
        desc = ['나스닥 100', '미국 방산', '이머징마켓(중국제외)', '하이일드 채권', '미국 장기채', '금', '초단기채(현금)']
        
    df = pd.DataFrame({
        '자산': tickers,
        '비중(%)': weights,
        '설명': desc
    })
    return df

# -----------------------------------------------------------------------------
# 5. AI 리스크 분석 함수 (DuckDuckGo + Gemini)
# -----------------------------------------------------------------------------
# [분석 함수: 수정된 get_latest_news() 호출]
def analyze_risk():
    news_data = get_latest_news()
    
    prompt = f"""
    아래는 방금 수집한 최신 금융 뉴스 헤드라인입니다:
    {news_data}
    
    이 헤드라인들을 바탕으로 우리 포트폴리오(나스닥 기술주, 하이일드 채권)에 
    영향을 줄 만한 '악재'가 있는지 분석해주세요.
    
    결과는 아래 양식으로 3줄 요약해줘:
    1. 시장 분위기: (평온 / 경계 / 공포 중 택1)
    2. 핵심 이슈: (헤드라인 중 가장 중요한 내용 한 문장)
    3. 대응 조언: (현재 포트폴리오 유지 또는 리밸런싱 검토 권장)
    """
    
    response = model.generate_content(prompt)
    return response.text

# ... (나머지 화면 표시 코드는 그대로) ...

# -----------------------------------------------------------------------------
# 6. 메인 앱 실행
# -----------------------------------------------------------------------------
def main():
    st.title("🛡️ 동적 자산배분 대시보드")
    st.markdown("시장 지표(가격, 이동평균, 스프레드)를 분석하여 현재 시장 국면을 진단하고 포트폴리오를 제안합니다.")
    st.divider()

    # 데이터 로딩
    with st.spinner('최신 시장 데이터를 불러오는 중입니다...'):
        price, ma200, spread, spread_date = get_financial_data()

    if price is None:
        return

    # A. 주요 지표 표시
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="QQQ 현재가", value=f"${price:.2f}", 
                  delta=f"{price - ma200:.2f} (vs 200MA)", delta_color="normal")
    with col2:
        st.metric(label="QQQ 200일 이동평균", value=f"${ma200:.2f}")
    with col3:
        st.metric(label="하이일드 스프레드 (Risk)", value=f"{spread:.2f}%", 
                  help=f"데이터 기준일: {spread_date}\n티커: BAMLH0A0HYM2")

    st.divider()

    # B. 시장 국면 진단
    real_regime_text, real_color, real_bg, real_text = determine_market_regime(price, ma200, spread)

    # 시뮬레이션 UI
    sim_col1, sim_col2 = st.columns([3, 1])
    with sim_col1:
        st.write("#### 🕹️ 상태 시뮬레이션")
        st.caption("현재 데이터와 무관하게, 특정 상황일 때의 포트폴리오를 미리 확인해볼 수 있습니다.")
        sim_mode = st.radio(
            "보고 싶은 시장 상태를 선택하세요:",
            ["실시간 진단 (자동)", "평온기 (Risk On)", "경계기 (Neutral/Caution)", "공포기 (Risk Off)"],
            horizontal=True,
            label_visibility="collapsed"
        )

    if sim_mode == "실시간 진단 (자동)":
        regime_text, color_name, bg_color, text_color = real_regime_text, real_color, real_bg, real_text
        is_simulated = False
    elif "평온기" in sim_mode:
        regime_text, color_name, bg_color, text_color = "평온기 (Risk On)", "green", "#d4edda", "#155724"
        is_simulated = True
    elif "공포기" in sim_mode:
        regime_text, color_name, bg_color, text_color = "공포기 (Risk Off)", "red", "#f8d7da", "#721c24"
        is_simulated = True
    else: 
        regime_text, color_name, bg_color, text_color = "경계기 (Neutral/Caution)", "orange", "#fff3cd", "#856404"
        is_simulated = True
    
    st.subheader(f"현재 시장 상태: {regime_text}")
    
    if is_simulated:
        st.warning("⚠️ 현재 이 화면은 '시뮬레이션 모드'입니다. 실제 시장 데이터 기반 진단이 아닙니다.")

    st.markdown(
        f'<div class="big-font" style="background-color: {bg_color}; color: {text_color}; border: 2px solid {text_color};">'
        f'{regime_text}'
        f'</div>', 
        unsafe_allow_html=True
    )

    with st.expander("📌 판단 기준 보기 (로직 상세)"):
        st.markdown(f"""
        - **현재 QQQ 가격**: ${price:.2f} {'🔴' if price < ma200 else '🟢'} (기준: 200MA ${ma200:.2f})
        - **현재 스프레드**: {spread:.2f}% {'🔴' if spread > 5.0 else ('🟢' if spread < 3.5 else '🟡')} (기준: 3.5% / 5.0%)
        
        **로직 정의:**
        1. **🟢 평온기 (Risk On)**: 스프레드 < 3.5% AND 주가 > 200MA
        2. **🔴 공포기 (Risk Off)**: 스프레드 > 5.0% AND 주가 < 200MA
        3. **🟠 경계기 (Caution)**: 그 외 (스프레드 3.5~5.0% OR 주가 < 200MA)
        """)

    st.divider()

    # C. 추천 포트폴리오
    st.subheader(f"📊 {regime_text} 추천 포트폴리오")
    portfolio_df = get_portfolio_weights(regime_text)
    
    col_chart, col_table = st.columns([1, 1])

    with col_chart:
        active_assets = portfolio_df[portfolio_df['비중(%)'] > 0]
        fig = px.pie(
            active_assets, 
            values='비중(%)', 
            names='자산', 
            title='자산 배분 비율',
            hole=0.4,
            color_discrete_sequence=px.colors.qualitative.Set3
        )
        fig.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig, use_container_width=True)

    with col_table:
        st.markdown("##### 상세 비중 및 설명")
        st.dataframe(
            portfolio_df, 
            hide_index=True,
            column_config={
                "비중(%)": st.column_config.ProgressColumn("비중(%)", format="%d%%", min_value=0, max_value=100)
            },
            use_container_width=True
        )
        
    st.divider()

    # D. AI 리스크 브리핑 (DuckDuckGo + Gemini)
    st.subheader("🤖 AI 리스크 브리핑 (DuckDuckGo News + Gemini 2.0)")
    st.caption("최신 뉴스를 검색(DuckDuckGo)하여 텍스트를 추출한 뒤, Gemini가 시장 위험도를 분석합니다. (API 검색 쿼터 미사용)")

    with st.container():
        if st.button("🚀 최신 뉴스 검색 및 리스크 분석 실행"):
            with st.spinner("DuckDuckGo에서 뉴스를 수집하고 Gemini가 분석 중입니다..."):
                result_text = analyze_latest_market_risks()
                
                st.markdown("#### 💡 분석 결과")
                st.markdown(f'<div class="ai-box">{result_text}</div>', unsafe_allow_html=True)

if __name__ == "__main__":

    main()

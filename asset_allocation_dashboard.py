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
def get_financial_data():
    try:
        # A. QQQ 데이터 및 200일 이동평균선
        end_date = datetime.now()
        start_date = end_date - timedelta(days=730)
        
        qqq = yf.Ticker("QQQ")
        qqq_hist = qqq.history(start=start_date, end=end_date)
        
        if qqq_hist.empty:
            st.error("QQQ 데이터를 가져올 수 없습니다.")
            return None, None, None, None

        qqq_hist['MA200'] = qqq_hist['Close'].rolling(window=200).mean()
        
        current_price = qqq_hist['Close'].iloc[-1]
        current_ma200 = qqq_hist['MA200'].iloc[-1]
        
        # B. 하이일드 스프레드 (FRED)
        fred_start = end_date - timedelta(days=365)
        spread_data = web.DataReader('BAMLH0A0HYM2', 'fred', fred_start, end_date)
        
        spread_data = spread_data.dropna()
        current_spread = spread_data['BAMLH0A0HYM2'].iloc[-1]
        spread_date = spread_data.index[-1].strftime('%Y-%m-%d')

        return current_price, current_ma200, current_spread, spread_date

    except Exception as e:
        st.error(f"데이터를 가져오는 중 오류가 발생했습니다: {e}")
        return None, None, None, None

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
def analyze_latest_market_risks():
    """
    DuckDuckGo로 뉴스를 검색하고, Gemini 2.0 Flash로 내용을 분석
    """
    if "GEMINI_API_KEY" not in st.secrets:
        return "⚠️ 오류: Streamlit Secrets에 'GEMINI_API_KEY'가 설정되지 않았습니다."
    
    try:
        # 1. DuckDuckGo 검색 실행
        keywords = ['US High Yield Spread', 'Nasdaq 100 Crash', 'Fed Rate Hike']
        collected_news = []
        
        with DDGS() as ddgs:
            for keyword in keywords:
                # 각 키워드별 최신 뉴스 3개씩 검색
                results = ddgs.news(keyword, region="wt-wt", safesearch="off", max_results=3)
                if results:
                    for r in results:
                        collected_news.append(f"- 제목: {r['title']}\n- 내용: {r['body']}\n- 출처: {r['url']}")

        if not collected_news:
            return "⚠️ 최신 뉴스를 검색하지 못했습니다. 잠시 후 다시 시도해주세요."

        news_text_block = "\n\n".join(collected_news)

        # 2. Gemini 설정 및 분석 요청 (Grounding 도구 미사용)
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        # 사용자가 요청한 모델 (없을 경우 1.5-flash 등으로 변경 가능)
        model = genai.GenerativeModel('gemini-2.5-flash') 
        print(news_text_block)
        prompt = f"""
        다음은 '하이일드 스프레드', '나스닥', '연준 금리'와 관련된 최신 뉴스 기사들입니다.
        
        [뉴스 데이터]
        {news_text_block}
        
        [요청사항]
        위 뉴스들을 종합적으로 분석해서, 현재 시장에 [하이일드 스프레드 급등]이나 [나스닥 200일선 이탈/폭락] 같은 심각한 리스크가 감지되는지 판단해줘.
        
        우선 가장 큰 뉴스 3가지를 제시해주고, 

        투자자 관점에서:
        1. 현재 시장의 핵심 리스크 요인이 무엇인지 요약하고,
        2. '평온', '경계', '공포' 중 어떤 분위기에 가까운지 의견을 제시해줘.
        3. 답변은 한국어로, 핵심만 3줄 내외로 간결하게 작성해줘.
        """
        
        response = model.generate_content(prompt)
        
        # 3. 결과 반환 (출처는 DuckDuckGo 결과에서 추출한 것들을 아래에 작게 표시 가능하지만, 여기선 깔끔하게 텍스트만)
        return response.text
        
    except Exception as e:
        return f"⚠️ 분석 중 오류가 발생했습니다: {str(e)}\n(duckduckgo-search 라이브러리가 설치되어 있는지 확인해주세요.)"

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
#%%import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor
import datetime
import time
import json
import numpy as np
import streamlit as st

# 페이지 기본 설정
st.set_page_config(
    page_title="SEPA Strategy Dashboard",
    page_icon="📈",
    layout="wide"
)

# 캐시 함수 설정
@st.cache_data(ttl=3600)  # 1시간 캐시
def load_sepa_stocks():
    """
    CSV 파일에서 SEPA 조건을 만족하는 주식 데이터를 로드합니다.
    """
    try:
        df = pd.read_csv('2024-11-18T12-28_export.csv')
        df['criteria_details'] = df['criteria_details'].apply(json.loads)
        return df
    except Exception as e:
        st.error(f"CSV 파일 로드 중 오류 발생: {str(e)}")
        return None
# %%
@st.cache_data(ttl=3600)
def calculate_technical_indicators(df):
    """기술적 지표를 계산합니다."""
    if len(df) < 200:
        return None

    try:
        df["MA5"] = df["Close"].rolling(window=5).mean()
        df["MA50"] = df["Close"].rolling(window=50).mean()
        df["MA150"] = df["Close"].rolling(window=150).mean()
        df["MA200"] = df["Close"].rolling(window=200).mean()
        return df
    except Exception as e:
        st.error(f"지표 계산 중 오류 발생: {str(e)}")
        return None

def verify_sepa_conditions(df, current_criteria):
    """현재 SEPA 조건이 여전히 유효한지 확인합니다."""
    if df is None or len(df) < 200:
        return False, {}, True

    try:
        latest = df.iloc[-1]
        month_ago = df.iloc[-30]

        new_criteria = {
            "현재가가 200일선 위": latest["Close"] > latest["MA200"],
            "150일선이 200일선 위": latest["MA150"] > latest["MA200"],
            "50일선이 150/200일선 위": (latest["MA50"] > latest["MA150"]) and (latest["MA50"] > latest["MA200"]),
            "현재가가 5일선 위": latest["Close"] > latest["MA5"],
            "200일선 상승 추세": latest["MA200"] > month_ago["MA200"],
            "52주 최저가 대비 30% 이상": (latest["Close"] / df["Low"].tail(252).min() - 1) > 0.3
        }

        conditions_changed = any(current_criteria[k] != new_criteria[k] for k in new_criteria)
        return all(new_criteria.values()), new_criteria, conditions_changed

    except Exception as e:
        st.error(f"SEPA 조건 검증 중 오류 발생: {str(e)}")
        return False, {}, True
# %%
@st.cache_data(ttl=3600)
def create_stock_chart(ticker, df):
    """주식 차트를 생성합니다."""
    fig = go.Figure()

    # 캔들스틱 차트
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df['Open'],
        high=df['High'],
        low=df['Low'],
        close=df['Close'],
        name='OHLC'
    ))

    # 이동평균선 추가
    colors = {'MA5': 'purple', 'MA50': 'blue', 'MA150': 'green', 'MA200': 'red'}
    for ma, color in colors.items():
        fig.add_trace(go.Scatter(
            x=df.index,
            y=df[ma],
            name=ma,
            line=dict(color=color)
        ))

    fig.update_layout(
        title=f"{ticker} Price and Moving Averages",
        yaxis_title="Price",
        xaxis_title="Date",
        height=600,
        template="plotly_white"
    )

    return fig

def analyze_stock(stock_data):
    """개별 주식의 현재 상태를 분석합니다."""
    try:
        ticker = stock_data['티커']
        stock = yf.Ticker(ticker)
        df = stock.history(period="1y")

        if df.empty:
            return None

        df = calculate_technical_indicators(df)
        if df is None:
            return None

        current_criteria = stock_data['criteria_details']
        still_valid, new_criteria, conditions_changed = verify_sepa_conditions(df, current_criteria)

        if still_valid:
            result = {
                "티커": ticker,
                "기업명": stock_data['기업명'],
                "섹터": stock_data['섹터'],
                "산업": stock_data['산업'],
                "현재가": df.iloc[-1]["Close"],
                "이전가": stock_data['현재가'],
                "가격변화율": ((df.iloc[-1]["Close"] / stock_data['현재가']) - 1) * 100,
                "시가총액": stock_data['시가총액(M)'],
                "조건변경": conditions_changed,
                "조건상세": new_criteria,
                "차트데이터": df
            }
            return result

        return None

    except Exception as e:
        st.error(f"{ticker} 분석 중 오류 발생: {str(e)}")
        return None
# %%
def main():
    st.title("SEPA Strategy Dashboard 📈")
    st.markdown("---")

    # 사이드바 설정
    st.sidebar.title("필터 옵션")
    
    # 데이터 로드
    with st.spinner('SEPA 주식 데이터 로드 중...'):
        sepa_df = load_sepa_stocks()
        if sepa_df is None or sepa_df.empty:
            st.error("SEPA 주식 데이터를 로드할 수 없습니다.")
            return

    # 섹터 필터
    sectors = ['전체'] + list(sepa_df['섹터'].unique())
    selected_sector = st.sidebar.selectbox('섹터 선택', sectors)

    # 시가총액 필터
    min_cap = float(sepa_df['시가총액(M)'].min())
    max_cap = float(sepa_df['시가총액(M)'].max())
    cap_range = st.sidebar.slider(
        '시가총액 범위 (백만 달러)',
        min_cap, max_cap,
        (min_cap, max_cap)
    )

    # 데이터 필터링
    filtered_df = sepa_df[
        (sepa_df['시가총액(M)'] >= cap_range[0]) &
        (sepa_df['시가총액(M)'] <= cap_range[1])
    ]
    if selected_sector != '전체':
        filtered_df = filtered_df[filtered_df['섹터'] == selected_sector]

    # 메인 대시보드
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("섹터별 분포")
        sector_fig = px.pie(
            sepa_df, 
            names='섹터', 
            values='시가총액(M)',
            title='섹터별 시가총액 분포'
        )
        st.plotly_chart(sector_fig)

    with col2:
        st.subheader("주요 통계")
        st.metric("총 종목 수", len(filtered_df))
        st.metric("평균 시가총액 (M$)", f"{filtered_df['시가총액(M)'].mean():,.2f}")
        st.metric("중간값 시가총액 (M$)", f"{filtered_df['시가총액(M)'].median():,.2f}")

    # 종목 상세 분석
    st.markdown("---")
    st.subheader("종목 상세 분석")
    
    selected_stock = st.selectbox(
        "분석할 종목 선택",
        filtered_df['티커'].tolist(),
        format_func=lambda x: f"{x} - {filtered_df[filtered_df['티커']==x]['기업명'].iloc[0]}"
    )

    if selected_stock:
        stock_data = filtered_df[filtered_df['티커'] == selected_stock].iloc[0]
        
        with st.spinner('종목 분석 중...'):
            analysis_result = analyze_stock(stock_data.to_dict())
            
            if analysis_result:
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    # 차트 표시
                    chart = create_stock_chart(
                        analysis_result['티커'],
                        analysis_result['차트데이터']
                    )
                    st.plotly_chart(chart, use_container_width=True)

                with col2:
                    # 종목 정보 표시
                    st.subheader("종목 정보")
                    metrics = {
                        "현재가": f"${analysis_result['현재가']:.2f}",
                        "가격변화율": f"{analysis_result['가격변화율']:.2f}%",
                        "시가총액": f"${analysis_result['시가총액']}M",
                        "섹터": analysis_result['섹터'],
                        "산업": analysis_result['산업']
                    }
                    
                    for key, value in metrics.items():
                        st.metric(key, value)

                # SEPA 조건 상세
                st.subheader("SEPA 조건 상세")
                conditions_df = pd.DataFrame({
                    "조건": analysis_result['조건상세'].keys(),
                    "충족여부": analysis_result['조건상세'].values()
                })
                st.dataframe(conditions_df)

    # 전체 종목 리스트
    st.markdown("---")
    st.subheader("전체 종목 리스트")
    st.dataframe(
        filtered_df[['티커', '기업명', '섹터', '산업', '현재가', '시가총액(M)']],
        use_container_width=True
    )

if __name__ == "__main__":
    main()
# %%

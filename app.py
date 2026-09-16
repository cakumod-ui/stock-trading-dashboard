import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta
# --- Page Configuration ---
st.set_page_config(page_title="Quant Event-Driven Dashboard", layout="wide")
st.title("📈 Quantitative Event-Driven Trading Dashboard")
st.markdown("Interactive stock chart with news event markers. Hover over markers to read the headlines.")
# --- Sidebar Controls ---
st.sidebar.header("Dashboard Controls")
ticker_input = st.sidebar.text_input("Enter US Stock Ticker (e.g., NVDA, MU, AAPL)", "NVDA").upper()
days_to_fetch = st.sidebar.slider("Historical Data Range (Days)", 30, 365, 180)
# --- Data Fetching Engine (Free APIs) ---
@st.cache_data(ttl=3600)
def fetch_stock_and_news(ticker, days):
    stock = yf.Ticker(ticker)
    # 1. Fetch Price Data
    end_date = datetime.today()
    start_date = end_date - timedelta(days=days)
    df_price = stock.history(start=start_date.strftime('%Y-%m-%d'), end=end_date.strftime('%Y-%m-%d'))
    df_price.reset_index(inplace=True)
    # 2. Fetch News Data (yfinance free tier returns recent news)
    news_data = stock.news
    news_list = []
    for article in news_data:
        pub_date = datetime.fromtimestamp(article['providerPublishTime'])
        news_list.append({
            'Date': pub_date.strftime('%Y-%m-%d'),
            'Headline': article['title'],
            'Link': article['link'],
            'Publisher': article['publisher']
        })
    df_news = pd.DataFrame(news_list)
    return df_price, df_news

if ticker_input:
    with st.spinner(f"Fetching market data and news for {ticker_input}..."):
        df_price, df_news = fetch_stock_and_news(ticker_input, days_to_fetch)
    if not df_price.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_price['Date'],
            y=df_price['Close'],
            mode='lines',
            name=f'{ticker_input} Close Price',
            line=dict(color='#1f77b4', width=2)
        ))
        if not df_news.empty:
            df_price['Date_Str'] = df_price['Date'].dt.strftime('%Y-%m-%d')
            merged_df = pd.merge(df_news, df_price[['Date_Str', 'Close']], left_on='Date', right_on='Date_Str', how='inner')
            fig.add_trace(go.Scatter(
                x=merged_df['Date'],
                y=merged_df['Close'],
                mode='markers',
                name='News Events',
                marker=dict(color='red', size=12, symbol='star', line=dict(color='white', width=1)),
                hoverinfo='text',
                text=merged_df['Publisher'] + ": " + merged_df['Headline']
            ))
        fig.update_layout(
            title=f"{ticker_input} Price Action & Event Triggers",
            xaxis_title="Date",
            yaxis_title="Close Price (USD)",
            hovermode="closest",
            template="plotly_dark",
            height=600
        )
        col1, col2 = st.columns([2, 1])
        with col1:
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            st.subheader(f"🗞️ Latest News for {ticker_input}")
            if not df_news.empty:
                for idx, row in df_news.iterrows():
                    st.markdown(f"**{row['Date']}**")
                    st.markdown(f"[{row['Headline']}]({row['Link']}) *(Source: {row['Publisher']})*")
                    st.divider()
            else:
                st.write("No recent news found for this ticker.")
    else:
        st.error("Failed to fetch data. Please check the ticker symbol.")

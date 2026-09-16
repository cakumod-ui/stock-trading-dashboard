import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta
import os

# --- Page Configuration ---
st.set_page_config(page_title="Quant Event-Driven Dashboard", layout="wide")
st.title("📈 Quantitative Event-Driven Trading Dashboard")
st.markdown("Interactive stock chart with algorithmic news event markers. News data powered by custom deduplication engine.")

# --- Sidebar Controls ---
st.sidebar.header("Dashboard Controls")
ticker_input = st.sidebar.text_input("Enter US Stock Ticker (e.g., NVDA, MU, AAPL)", "NVDA").upper()
days_to_fetch = st.sidebar.slider("Historical Data Range (Days)", 30, 365, 180)

# --- Built-In Data Engine Function ---
def build_clean_database():
    """Builds and deduplicates news data natively without needing external process calls."""
    data_polygon = {
        'Ticker': ['NVDA', 'NVDA', 'MU'],
        'Date': ['2026-09-08 09:30:00', '2026-09-08 09:45:00', '2026-09-09 14:00:00'],
        'Headline': ['Nvidia announces new AI chip', 'NVDA unveils next-gen AI hardware', 'Micron expanding capacity'],
        'URL': ['https://polygon.io/news/1', 'https://polygon.io/news/2', 'https://polygon.io/news/3'],
        'Source': ['Polygon'] * 3
    }
    data_fmp = {
        'Ticker': ['NVDA', 'AAPL', 'MU'],
        'Date': ['2026-09-08 10:15:00', '2026-09-08 11:00:00', '2026-09-09 14:00:00'],
        'Headline': ['Nvidia stock surges on AI announcement', 'Apple releases new iPhone', 'Micron expanding capacity'],
        'URL': ['https://fmp.com/news/1', 'https://fmp.com/news/2', 'https://polygon.io/news/3'], 
        'Source': ['FMP'] * 3
    }
    data_kaggle = {
        'Ticker': ['MU', 'NVDA', 'TSLA'],
        'Date': ['2026-09-09 16:30:00', '2026-09-10 08:00:00', '2026-09-10 09:00:00'],
        'Headline': ['Micron to build new factory in US', 'Nvidia AI chips sold out', 'Tesla announces new car'],
        'URL': ['https://kaggle.com/news/1', 'https://kaggle.com/news/2', 'https://kaggle.com/news/3'],
        'Source': ['Kaggle'] * 3
    }

    df_poly = pd.DataFrame(data_polygon)
    df_fmp = pd.DataFrame(data_fmp)
    df_kag = pd.DataFrame(data_kaggle)

    combined_df = pd.concat([df_poly, df_fmp, df_kag], ignore_index=True)
    
    # Deduplication Steps
    clean_df = combined_df.drop_duplicates(subset=['URL'], keep='first')
    clean_df = clean_df.drop_duplicates(subset=['Headline'], keep='first')
    
    clean_df['Date_Temp'] = pd.to_datetime(clean_df['Date'])
    clean_df['Date_Only'] = clean_df['Date_Temp'].dt.date
    final_df = clean_df.drop_duplicates(subset=['Ticker', 'Date_Only'], keep='first')
    final_df = final_df.drop(columns=['Date_Temp', 'Date_Only']).sort_values(by=['Date'])
    
    # Save CSV
    final_df.to_csv("Clean_Algo_News_Database.csv", index=False)

# --- Sidebar Button ---
st.sidebar.divider()
st.sidebar.subheader("⚙️ Data Engine")
st.sidebar.markdown("Click below to run the deduplication pipeline and build a clean news database.")

if st.sidebar.button("Build Clean Database"):
    with st.spinner("Running Deduplication Engine..."):
        build_clean_database()
        st.cache_data.clear()
        st.sidebar.success("✅ Database built successfully!")
        st.rerun()  # Forces Streamlit to reload immediately and display the new data!

# --- 1. Fetch Price Data ---
@st.cache_data(ttl=3600)
def fetch_stock_price(ticker, days):
    stock = yf.Ticker(ticker)
    end_date = datetime.today()
    start_date = end_date - timedelta(days=days)
    
    df_price = stock.history(start=start_date.strftime('%Y-%m-%d'), end=end_date.strftime('%Y-%m-%d'))
    
    if not df_price.empty:
        df_price.reset_index(inplace=True)
        date_col = 'Date' if 'Date' in df_price.columns else 'Datetime'
        df_price['Date'] = pd.to_datetime(df_price[date_col]).dt.tz_localize(None).astype('datetime64[ns]')
        df_price = df_price.sort_values('Date')
        
    return df_price

# --- 2. Fetch Saved News Data ---
@st.cache_data(ttl=5)
def fetch_saved_news(ticker):
    file_path = "Clean_Algo_News_Database.csv"
    
    if os.path.exists(file_path):
        try:
            df_news = pd.read_csv(file_path)
            df_news = df_news[df_news['Ticker'] == ticker].copy()
            
            if not df_news.empty:
                df_news['Date'] = pd.to_datetime(df_news['Date']).dt.tz_localize(None).astype('datetime64[ns]')
                df_news = df_news.sort_values('Date')
                
            return df_news
            
        except Exception as e:
            st.error(f"Error reading database: {e}")
            return pd.DataFrame()
    else:
        return pd.DataFrame()

# --- Application Logic ---
if ticker_input:
    with st.spinner(f"Fetching market data and scanning database for {ticker_input}..."):
        df_price = fetch_stock_price(ticker_input, days_to_fetch)
        df_news = fetch_saved_news(ticker_input)

    if not df_price.empty:
        fig = go.Figure()

        # Add Price Line
        fig.add_trace(go.Scatter(
            x=df_price['Date'], 
            y=df_price['Close'],
            mode='lines',
            name=f'{ticker_input} Close Price',
            line=dict(color='#00ff9d', width=2)
        ))

        # Add News Markers
        if not df_news.empty:
            merged_df = pd.merge_asof(
                df_news, 
                df_price[['Date', 'Close']], 
                on='Date', 
                direction='nearest'
            )

            fig.add_trace(go.Scatter(
                x=merged_df['Date'],
                y=merged_df['Close'],
                mode='markers',
                name='News Events',
                marker=dict(color='#ff003c', size=12, symbol='star', line=dict(color='white', width=1.5)),
                hoverinfo='text',
                text=merged_df['Date'].dt.strftime('%Y-%m-%d') + "<br>" + merged_df['Source'] + ": " + merged_df['Headline']
            ))

        # Layout Formatting
        fig.update_layout(
            title=f"{ticker_input} Price Action & Event Triggers",
            xaxis_title="Date",
            yaxis_title="Close Price (USD)",
            hovermode="closest",
            template="plotly_dark",
            height=600,
            margin=dict(l=20, r=20, t=50, b=20)
        )
        
        # Render Columns
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.plotly_chart(fig, use_container_width=True)
            
        with col2:
            st.subheader(f"🗞️ Master Database Timeline")
            
            if df_news.empty:
                st.warning("⚠️ No news data found in database. Click 'Build Clean Database' in the sidebar!")
            else:
                df_news_display = df_news.sort_values('Date', ascending=False)
                for idx, row in df_news_display.iterrows():
                    date_str = row['Date'].strftime('%b %d, %Y')
                    st.markdown(f"**{date_str}** — *{row['Source']}*")
                    st.markdown(f"[{row['Headline']}]({row['URL']})")
                    st.divider()
    else:
        st.error("Failed to fetch price data. Check the ticker symbol.")

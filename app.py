import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta
import subprocess
import os

# --- Page Configuration ---
st.set_page_config(page_title="Quant Event-Driven Dashboard", layout="wide")
st.title("📈 Quantitative Event-Driven Trading Dashboard")
st.markdown("Interactive stock chart with algorithmic news event markers. News data powered by custom deduplication engine.")

# --- Sidebar Controls ---
st.sidebar.header("Dashboard Controls")
ticker_input = st.sidebar.text_input("Enter US Stock Ticker (e.g., NVDA, MU, AAPL)", "NVDA").upper()
days_to_fetch = st.sidebar.slider("Historical Data Range (Days)", 30, 365, 180)

# --- Data Engine Control ---
st.sidebar.divider()
st.sidebar.subheader("⚙️ Data Engine")
st.sidebar.markdown("Click below to run the deduplication pipeline and build a clean news database.")

if st.sidebar.button("Build Clean Database"):
    with st.spinner("Running Deduplication Engine..."):
        # This tells the cloud server to run your engine file!
        subprocess.run(["python", "build_database.py"])
        st.sidebar.success("✅ Clean_Algo_News_Database.csv created successfully!")
        
        # Clear Streamlit's cache so it reloads the new data instantly
        st.cache_data.clear()

# --- 1. Fetch Price Data ---
@st.cache_data(ttl=3600)
def fetch_stock_price(ticker, days):
    stock = yf.Ticker(ticker)
    end_date = datetime.today()
    start_date = end_date - timedelta(days=days)
    
    # Fetch historical data
    df_price = stock.history(start=start_date.strftime('%Y-%m-%d'), end=end_date.strftime('%Y-%m-%d'))
    
    if not df_price.empty:
        df_price.reset_index(inplace=True)
        # Handle Yahoo Finance column variations
        date_col = 'Date' if 'Date' in df_price.columns else 'Datetime'
        
        # Standardize strictly to timezone-naive datetime objects with nanosecond resolution
        df_price['Date'] = pd.to_datetime(df_price[date_col]).dt.tz_localize(None).astype('datetime64[ns]')
        
        # Sort values chronologically
        df_price = df_price.sort_values('Date')
        
    return df_price

# --- 2. Fetch Custom Built News Data ---
@st.cache_data(ttl=5) # Fast refresh to see new data
def fetch_saved_news(ticker):
    file_path = "Clean_Algo_News_Database.csv"
    
    # Check if the file actually exists
    if os.path.exists(file_path):
        try:
            # Read the CSV your engine just built
            df_news = pd.read_csv(file_path)
            
            # Filter news specifically for the chosen ticker (so AAPL news doesn't show on NVDA chart)
            df_news = df_news[df_news['Ticker'] == ticker].copy()
            
            if not df_news.empty:
                # STRIP TIMEZONES and enforce nanosecond resolution for clean merge with Yahoo Finance prices
                df_news['Date'] = pd.to_datetime(df_news['Date']).dt.tz_localize(None).astype('datetime64[ns]')
                df_news = df_news.sort_values('Date')
                
            return df_news
            
        except Exception as e:
            st.error(f"Error reading database: {e}")
            return pd.DataFrame()
    else:
        # Returns an empty dataframe if you haven't clicked the build button yet
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

        # --- The Smart Merge: Snapping News to Trading Days ---
        if not df_news.empty:
            
            merged_df = pd.merge_asof(
                df_news, 
                df_price[['Date', 'Close']], 
                on='Date', 
                direction='nearest'
            )

            # Add interactive markers exactly on the line
            fig.add_trace(go.Scatter(
                x=merged_df['Date'],
                y=merged_df['Close'],
                mode='markers',
                name='News Events',
                marker=dict(color='#ff003c', size=12, symbol='star', line=dict(color='white', width=1.5)),
                hoverinfo='text',
                text=merged_df['Date'].dt.strftime('%Y-%m-%d') + "<br>" + merged_df['Source'] + ": " + merged_df['Headline']
            ))

        # Chart Layout Formatting
        fig.update_layout(
            title=f"{ticker_input} Price Action & Event Triggers",
            xaxis_title="Date",
            yaxis_title="Close Price (USD)",
            hovermode="closest",
            template="plotly_dark",
            height=600,
            margin=dict(l=20, r=20, t=50, b=20)
        )
        
        # --- Render UI ---
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.plotly_chart(fig, use_container_width=True)
            
        with col2:
            st.subheader(f"🗞️ Master Database Timeline")
            
            if df_news.empty:
                st.warning("⚠️ No news data found in database. Click 'Build Clean Database' in the sidebar!")
            else:
                # Display newest first in the side column
                df_news_display = df_news.sort_values('Date', ascending=False)
                for idx, row in df_news_display.iterrows():
                    date_str = row['Date'].strftime('%b %d, %Y')
                    st.markdown(f"**{date_str}** — *{row['Source']}*")
                    st.markdown(f"[{row['Headline']}]({row['URL']})")
                    st.divider()
    else:
        st.error("Failed to fetch price data. Check the ticker symbol.")

import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta
import urllib.request
import xml.etree.ElementTree as ET

# --- Page Configuration ---
st.set_page_config(page_title="Quant Event-Driven Dashboard", layout="wide")
st.title("📈 Quantitative Event-Driven Trading Dashboard")
st.markdown("Interactive stock chart with news event markers. Weekend news automatically snaps to the nearest trading day.")

# --- Sidebar Controls ---
st.sidebar.header("Dashboard Controls")
ticker_input = st.sidebar.text_input("Enter US Stock Ticker (e.g., NVDA, MU, AAPL)", "NVDA").upper()
days_to_fetch = st.sidebar.slider("Historical Data Range (Days)", 30, 365, 180)

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

# --- 2. Fetch News Data (Google RSS Engine) ---
@st.cache_data(ttl=3600)
def fetch_google_news(ticker, days):
    # Google RSS supports "when:180d" to search a specific timeframe
    url = f'https://news.google.com/rss/search?q={ticker}+stock+when:{days}d&hl=en-US&gl=US&ceid=US:en'
    
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    news_list = []
    
    try:
        response = urllib.request.urlopen(req)
        xml_data = response.read()
        root = ET.fromstring(xml_data)
        
        # Parse XML items (Limit to top 50 to avoid cluttering the graph)
        for item in root.findall('.//item')[:50]:
            title = item.find('title').text if item.find('title') is not None else "No Title"
            link = item.find('link').text if item.find('link') is not None else "#"
            pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ""
            
            if pub_date:
                try:
                    # Parse Google's GMT date format
                    dt = datetime.strptime(pub_date, '%a, %d %b %Y %H:%M:%S %Z')
                except ValueError:
                    # Fallback parser
                    dt = pd.to_datetime(pub_date)
            else:
                continue
            
            news_list.append({
                'Date': dt,
                'Headline': title.split('-')[0].strip(),
                'Publisher': title.split('-')[-1].strip() if '-' in title else 'Google News',
                'Link': link
            })
            
    except Exception:
        pass # Fails silently and continues to return empty dataframe
        
    df_news = pd.DataFrame(news_list)
    
    if not df_news.empty:
        # STRIP TIMEZONES and enforce nanosecond resolution for clean merge with Yahoo Finance prices
        df_news['Date'] = pd.to_datetime(df_news['Date']).dt.tz_localize(None).astype('datetime64[ns]')
        df_news = df_news.sort_values('Date')
        
    return df_news

# --- Application Logic ---
if ticker_input:
    with st.spinner(f"Fetching market data and scanning news for {ticker_input}..."):
        df_price = fetch_stock_price(ticker_input, days_to_fetch)
        df_news = fetch_google_news(ticker_input, days_to_fetch)

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
                marker=dict(color='#ff003c', size=10, symbol='circle', line=dict(color='white', width=1.5)),
                hoverinfo='text',
                text=merged_df['Date'].dt.strftime('%Y-%m-%d') + "<br>" + merged_df['Publisher'] + ": " + merged_df['Headline']
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
            st.subheader(f"🗞️ News Timeline ({days_to_fetch} Days)")
            if not df_news.empty:
                # Display newest first in the side column
                df_news_display = df_news.sort_values('Date', ascending=False)
                for idx, row in df_news_display.iterrows():
                    date_str = row['Date'].strftime('%b %d, %Y')
                    st.markdown(f"**{date_str}** — *{row['Publisher']}*")
                    st.markdown(f"[{row['Headline']}]({row['Link']})")
                    st.divider()
            else:
                st.write("No news data found for this timeframe.")
    else:
        st.error("Failed to fetch price data. Check the ticker symbol.")

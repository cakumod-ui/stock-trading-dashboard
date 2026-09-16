import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta
import urllib.request
import xml.etree.ElementTree as ET
import os

# --- Page Configuration ---
st.set_page_config(page_title="Quant Event-Driven Dashboard", layout="wide")
st.title("📈 Quantitative Event-Driven Trading Dashboard")
st.markdown("Interactive stock chart with algorithmic news event markers. Select a NASDAQ stock from the dropdown below.")

# --- Curated Master List of NASDAQ Listed Stocks for Dropdown ---
nasdaq_stocks = {
    "NVDA": "Nvidia Corporation (NVDA)",
    "MU": "Micron Technology, Inc. (MU)",
    "AAPL": "Apple Inc. (AAPL)",
    "MSFT": "Microsoft Corporation (MSFT)",
    "GOOGL": "Alphabet Inc. / Google (GOOGL)",
    "AMZN": "Amazon.com, Inc. (AMZN)",
    "META": "Meta Platforms, Inc. (META)",
    "TSLA": "Tesla, Inc. (TSLA)",
    "NFLX": "Netflix, Inc. (NFLX)",
    "AMD": "Advanced Micro Devices, Inc. (AMD)",
    "INTC": "Intel Corporation (INTC)",
    "QCOM": "QUALCOMM Incorporated (QCOM)",
    "CSCO": "Cisco Systems, Inc. (CSCO)",
    "PEP": "PepsiCo, Inc. (PEP)",
    "COST": "Costco Wholesale Corporation (COST)",
    "AVGO": "Broadcom Inc. (AVGO)",
    "ADBE": "Adobe Inc. (ADBE)",
    "TXN": "Texas Instruments Incorporated (TXN)"
}

# --- Sidebar Controls ---
st.sidebar.header("Dashboard Controls")

# Dropdown selector instead of text input
selected_display_name = st.sidebar.selectbox(
    "Select NASDAQ Stock", 
    options=list(nasdaq_stocks.values()),
    index=0 # Defaults to Nvidia
)

# Extract ticker symbol from the selection (e.g., "Nvidia Corporation (NVDA)" -> "NVDA")
ticker_input = [k for k, v in nasdaq_stocks.items() if v == selected_display_name][0]

days_to_fetch = st.sidebar.slider("Historical Data Range (Days)", 30, 365, 180)

# --- Built-In LIVE Data Engine ---
def build_clean_database(ticker, days):
    """Fetches real live news via Google RSS for the selected ticker, deduplicates it, and saves."""
    url = f'https://news.google.com/rss/search?q={ticker}+stock+when:{days}d&hl=en-US&gl=US&ceid=US:en'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    
    news_list = []
    try:
        response = urllib.request.urlopen(req)
        xml_data = response.read()
        root = ET.fromstring(xml_data)
        
        # Pull up to 100 recent articles
        for item in root.findall('.//item')[:100]:
            title = item.find('title').text if item.find('title') is not None else "No Title"
            link = item.find('link').text if item.find('link') is not None else "#"
            pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ""
            
            if pub_date:
                try:
                    dt = datetime.strptime(pub_date, '%a, %d %b %Y %H:%M:%S %Z')
                except ValueError:
                    dt = pd.to_datetime(pub_date)
            else:
                continue
                
            news_list.append({
                'Ticker': ticker,
                'Date': dt,
                'Headline': title.split('-')[0].strip(),
                'Source': title.split('-')[-1].strip() if '-' in title else 'Google News',
                'URL': link
            })
    except Exception as e:
        st.error(f"Failed to fetch live data: {e}")
        return

    if not news_list:
        return
        
    combined_df = pd.DataFrame(news_list)
    
    # --- DEDUPLICATION ENGINE ---
    clean_df = combined_df.drop_duplicates(subset=['URL'], keep='first')
    clean_df = clean_df.drop_duplicates(subset=['Headline'], keep='first')
    
    clean_df['Date_Temp'] = pd.to_datetime(clean_df['Date'])
    clean_df['Date_Only'] = clean_df['Date_Temp'].dt.date
    final_df = clean_df.drop_duplicates(subset=['Ticker', 'Date_Only'], keep='first')
    
    final_df = final_df.drop(columns=['Date_Temp', 'Date_Only']).sort_values(by=['Date'])
    final_df.to_csv(f"Clean_Algo_News_{ticker}.csv", index=False)


# --- Sidebar Button ---
st.sidebar.divider()
st.sidebar.subheader("⚙️ Live Data Engine")
st.sidebar.markdown(f"Click below to fetch and deduplicate live articles for **{ticker_input}**.")

if st.sidebar.button(f"Fetch & Build {ticker_input} Database"):
    with st.spinner(f"Scraping the web and running deduplication for {ticker_input}..."):
        build_clean_database(ticker_input, days_to_fetch)
        st.cache_data.clear()
        st.sidebar.success(f"✅ {ticker_input} database built successfully!")
        st.rerun()

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
    file_path = f"Clean_Algo_News_{ticker}.csv"
    
    if os.path.exists(file_path):
        try:
            df_news = pd.read_csv(file_path)
            if not df_news.empty:
                df_news['Date'] = pd.to_datetime(df_news['Date']).dt.tz_localize(None).astype('datetime64[ns]')
                df_news = df_news.sort_values('Date')
            return df_news
        except Exception:
            return pd.DataFrame()
    else:
        return pd.DataFrame()

# --- Application Logic ---
if ticker_input:
    with st.spinner(f"Rendering dashboard for {selected_display_name}..."):
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

        # Add News Markers with Smart Merge
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
            title=f"{selected_display_name} Price Action & Event Triggers",
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
                st.warning(f"⚠️ No database found for {ticker_input}. Click **'Fetch & Build'** in the sidebar!")
            else:
                st.success(f"Loaded {len(df_news)} deduplicated events.")
                df_news_display = df_news.sort_values('Date', ascending=False)
                for idx, row in df_news_display.iterrows():
                    date_str = row['Date'].strftime('%b %d, %Y')
                    st.markdown(f"**{date_str}** — *{row['Source']}*")
                    st.markdown(f"[{row['Headline']}]({row['URL']})")
                    st.divider()
    else:
        st.error("Failed to fetch price data. Check the stock ticker.")

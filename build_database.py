import pandas as pd
from datetime import datetime

print("🚀 Starting the Quant News Deduplication Engine...\n")

# ==========================================
# STEP 1: Simulate Downloading Data
# (Later, you will replace this by reading actual CSVs or APIs)
# ==========================================

# Source 1: Polygon.io (NASDAQ News)
data_polygon = {
    'Ticker': ['NVDA', 'NVDA', 'MU'],
    'Date': ['2026-09-08 09:30:00', '2026-09-08 09:45:00', '2026-09-09 14:00:00'],
    'Headline': ['Nvidia announces new AI chip', 'NVDA unveils next-gen AI hardware', 'Micron expanding capacity'],
    'URL': ['https://polygon.io/news/1', 'https://polygon.io/news/2', 'https://polygon.io/news/3'],
    'Source': ['Polygon'] * 3
}
df_polygon = pd.DataFrame(data_polygon)

# Source 2: Financial Modeling Prep (Dow Jones News)
data_fmp = {
    'Ticker': ['NVDA', 'AAPL', 'MU'],
    'Date': ['2026-09-08 10:15:00', '2026-09-08 11:00:00', '2026-09-09 14:00:00'],
    # Notice the MU headline/URL is an EXACT duplicate of Polygon's
    'Headline': ['Nvidia stock surges on AI announcement', 'Apple releases new iPhone', 'Micron expanding capacity'],
    'URL': ['https://fmp.com/news/1', 'https://fmp.com/news/2', 'https://polygon.io/news/3'], 
    'Source': ['FMP'] * 3
}
df_fmp = pd.DataFrame(data_fmp)

# Source 3: Kaggle Bulk Dataset
data_kaggle = {
    'Ticker': ['MU', 'NVDA', 'TSLA'],
    'Date': ['2026-09-09 16:30:00', '2026-09-10 08:00:00', '2026-09-10 09:00:00'],
    'Headline': ['Micron to build new factory in US', 'Nvidia AI chips sold out', 'Tesla announces new car'],
    'URL': ['https://kaggle.com/news/1', 'https://kaggle.com/news/2', 'https://kaggle.com/news/3'],
    'Source': ['Kaggle'] * 3
}
df_kaggle = pd.DataFrame(data_kaggle)


# ==========================================
# STEP 2: Combine All Sources
# ==========================================
# Instead of doing this manually, Pandas smashes them all together instantly.
combined_df = pd.concat([df_polygon, df_fmp, df_kaggle], ignore_index=True)

print(f"📊 Total raw articles collected: {len(combined_df)}")


# ==========================================
# STEP 3: Level 1 Deduplication (Exact Matches)
# ==========================================
# If two articles have the exact same URL or exact same Headline, delete the duplicate.
clean_df = combined_df.drop_duplicates(subset=['URL'], keep='first')
clean_df = clean_df.drop_duplicates(subset=['Headline'], keep='first')

print(f"🧹 Articles after removing exact duplicates: {len(clean_df)}")


# ==========================================
# STEP 4: Level 2 Deduplication (Event-Based for Algos)
# ==========================================
# For trading, we only want ONE marker on the graph per stock, per day.
# First, we need to standardize the date and extract JUST the day (no hours/minutes)
clean_df['Date'] = pd.to_datetime(clean_df['Date'])
clean_df['Date_Only'] = clean_df['Date'].dt.date

# Now, drop duplicates so we only keep the FIRST news article for a ticker on that specific day
final_algo_df = clean_df.drop_duplicates(subset=['Ticker', 'Date_Only'], keep='first')

print(f"🎯 Final actionable events for the trading algorithm: {len(final_algo_df)}\n")


# ==========================================
# STEP 5: View & Export the Final Database
# ==========================================
# Drop the temporary 'Date_Only' column to keep it clean
final_algo_df = final_algo_df.drop(columns=['Date_Only']).sort_values(by=['Date'])

print("✅ FINAL DATABASE:")
print(final_algo_df.to_string(index=False))

# Export to CSV so your Streamlit dashboard can read it!
output_filename = "Clean_Algo_News_Database.csv"
final_algo_df.to_csv(output_filename, index=False)
print(f"\n💾 Saved successfully to {output_filename}")

import csv
import os

def load_cash_universe(path: str = "data/cash_universe.csv"):
    if not os.path.exists(path):
        return []
    symbols = []
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            symbol = (row.get("symbol") or "").strip().upper()
            if symbol and symbol not in symbols:
                symbols.append(symbol)
    return symbols

def load_fo_universe(path: str = "data/fo_universe.csv"):
    if not os.path.exists(path):
        return []
    symbols = []
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            symbol = (row.get("symbol") or "").strip().upper()
            if symbol and symbol not in symbols:
                symbols.append(symbol)
    return symbols

if __name__ == "__main__":
    cash = load_cash_universe()
    fo = load_fo_universe()
    print("cash_count:", len(cash))
    print("fo_count:", len(fo))
    print("cash_sample:", cash[:10])
    print("fo_sample:", fo[:10])

# ====================== CONFIG ======================

PAPER_TRADING = True          # True = симуляция, False = реальная торговля (опасно!)

EXCHANGE = "binance"
SYMBOL = "BTC/USDT"
TIMEFRAME = "15m"

FAST_SMA = 10
SLOW_SMA = 30

POSITION_SIZE_USDT = 50
STARTING_BALANCE = 50.0

STOP_LOSS_PCT = 0.015         # 1.5%
TAKE_PROFIT_PCT = 0.03        # 3% (1:2)

# API ключи только если PAPER_TRADING = False
API_KEY = ""
API_SECRET = ""

# ====================================================

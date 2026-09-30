# ====================== CONFIG ======================

PAPER_TRADING = True          # True = симуляция, False = реальная торговля (опасно!)

EXCHANGE = "binance"
SYMBOL = "BTC/USDT"
TIMEFRAME = "1m"              # быстрее решения, не ждём днями

FAST_SMA = 5
SLOW_SMA = 13

POSITION_SIZE_USDT = 50
STARTING_BALANCE = 50.0

STOP_LOSS_PCT = 0.008         # 0.8% — короче на 1m
TAKE_PROFIT_PCT = 0.016       # 1.6% (1:2)

POLL_SECONDS = 8              # как часто смотреть рынок

# API ключи только если PAPER_TRADING = False
API_KEY = ""
API_SECRET = ""

# ====================================================

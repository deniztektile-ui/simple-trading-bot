# ====================== CONFIG ======================

# Режим работы
PAPER_TRADING = True          # True = симуляция, False = реальная торговля (опасно!)

# Биржа и пара
EXCHANGE = "binance"
SYMBOL = "BTC/USDT"
TIMEFRAME = "15m"             # 1m, 5m, 15m, 1h, 4h, 1d

# Стратегия Moving Average
FAST_SMA = 10
SLOW_SMA = 30

# Риск-менеджмент
POSITION_SIZE_USDT = 50       # размер позиции в USDT (для paper)
STOP_LOSS_PCT = 0.02          # 2% stop-loss
TAKE_PROFIT_PCT = 0.04         # 4% take-profit

# API ключи (только если PAPER_TRADING = False)
API_KEY = ""
API_SECRET = ""

# ====================================================

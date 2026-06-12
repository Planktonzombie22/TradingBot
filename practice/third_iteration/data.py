import yfinance as yf
import config as cfg

df = yf.download(cfg.MARKET, period=cfg.PERIOD, interval=cfg.INTERVAL, multi_level_index=False)
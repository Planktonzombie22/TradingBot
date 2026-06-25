from indicators import SMA
from strategy import Strategy

class SMACrossover(Strategy):
    def __init__(self, data, period1, period2):
        self.SMA1 = SMA(period1)
        self.SMA2 = SMA(period2)
        self.data = data

    def signals(self, data):
        ...
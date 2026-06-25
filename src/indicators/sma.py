from indicator import Indicator

class SMA(Indicator):
    def __init__(self, period):
        self.period = period

    def return_indicator_data(self, data):
        return data["Close"].rolling(self.period).mean()

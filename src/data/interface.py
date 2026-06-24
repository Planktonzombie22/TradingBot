class DataFeed:
    def get_historical(self, symbol, start, end, interval):
        raise NotImplementedError
    
    def get_stream(self, symbol):
        raise NotImplementedError
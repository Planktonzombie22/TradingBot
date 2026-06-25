from abc import ABC, abstractmethod

class Indicator(ABC):
    @abstractmethod
    def return_indicator_data(self, data):
        raise NotImplementedError()
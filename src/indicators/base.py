from abc import ABC, abstractmethod

import pandas as pd


class Indicator(ABC):
    @abstractmethod
    def calculate(self) -> pd.Series:
        raise NotImplementedError

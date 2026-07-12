from dataclasses import dataclass, field
from importlib.util import find_spec
from typing import Mapping, Sequence

import pandas as pd


def scipy_available() -> bool:
    return find_spec("scipy") is not None


def statsmodels_available() -> bool:
    return find_spec("statsmodels") is not None


def require_scipy_support() -> None:
    if not scipy_available():
        raise RuntimeError("scipy statistics require the research dependency profile: pip install -r requirements/research.txt")


def require_statsmodels_support() -> None:
    if not statsmodels_available():
        raise RuntimeError("statsmodels research tools require the research dependency profile: pip install -r requirements/research.txt")


@dataclass(frozen=True)
class ConfidenceInterval:
    mean: float
    lower: float
    upper: float
    confidence: float
    sample_size: int

    def to_dict(self) -> dict:
        return {
            "mean": self.mean,
            "lower": self.lower,
            "upper": self.upper,
            "confidence": self.confidence,
            "sample_size": self.sample_size,
        }


@dataclass(frozen=True)
class CointegrationTestResult:
    statistic: float
    p_value: float
    critical_values: Mapping[str, float]
    passed: bool
    alpha: float

    def to_dict(self) -> dict:
        return {
            "statistic": self.statistic,
            "p_value": self.p_value,
            "critical_values": dict(self.critical_values),
            "passed": self.passed,
            "alpha": self.alpha,
        }


@dataclass(frozen=True)
class FactorExposureResult:
    alpha: float
    betas: Mapping[str, float]
    p_values: Mapping[str, float]
    r_squared: float
    observations: int

    def to_dict(self) -> dict:
        return {
            "alpha": self.alpha,
            "betas": dict(self.betas),
            "p_values": dict(self.p_values),
            "r_squared": self.r_squared,
            "observations": self.observations,
        }


@dataclass(frozen=True)
class MultipleTestingResult:
    method: str
    alpha: float
    adjusted_p_values: tuple[float, ...]
    rejected: tuple[bool, ...]

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "alpha": self.alpha,
            "adjusted_p_values": list(self.adjusted_p_values),
            "rejected": list(self.rejected),
        }


def confidence_interval(values: Sequence[float] | pd.Series, confidence: float = 0.95) -> ConfidenceInterval:
    require_scipy_support()
    from scipy import stats

    series = pd.Series(values, dtype="float64").dropna()
    if series.empty:
        return ConfidenceInterval(0.0, 0.0, 0.0, confidence, 0)
    mean = float(series.mean())
    if len(series) < 2:
        return ConfidenceInterval(mean, mean, mean, confidence, len(series))
    standard_error = float(stats.sem(series))
    margin = float(stats.t.ppf((1 + confidence) / 2, len(series) - 1) * standard_error)
    return ConfidenceInterval(mean, mean - margin, mean + margin, confidence, len(series))


def cointegration_test(
    first: Sequence[float] | pd.Series,
    second: Sequence[float] | pd.Series,
    alpha: float = 0.05,
) -> CointegrationTestResult:
    require_statsmodels_support()
    from statsmodels.tsa.stattools import coint

    aligned = pd.concat(
        [pd.Series(first, dtype="float64"), pd.Series(second, dtype="float64")],
        axis=1,
    ).dropna()
    if len(aligned) < 3:
        return CointegrationTestResult(0.0, 1.0, {}, False, alpha)
    statistic, p_value, critical_values = coint(aligned.iloc[:, 0], aligned.iloc[:, 1])
    critical_map = {"1%": float(critical_values[0]), "5%": float(critical_values[1]), "10%": float(critical_values[2])}
    return CointegrationTestResult(float(statistic), float(p_value), critical_map, float(p_value) <= alpha, alpha)


def factor_exposure(
    returns: Sequence[float] | pd.Series,
    factors: pd.DataFrame,
) -> FactorExposureResult:
    require_statsmodels_support()
    import statsmodels.api as sm

    target = pd.Series(returns, dtype="float64", name="returns")
    data = pd.concat([target, factors.astype("float64")], axis=1).dropna()
    if data.empty:
        return FactorExposureResult(0.0, {}, {}, 0.0, 0)
    y = data.iloc[:, 0]
    x = sm.add_constant(data.iloc[:, 1:])
    model = sm.OLS(y, x).fit()
    params = model.params.to_dict()
    p_values = model.pvalues.to_dict()
    return FactorExposureResult(
        alpha=float(params.pop("const", 0.0)),
        betas={name: float(value) for name, value in params.items()},
        p_values={name: float(value) for name, value in p_values.items()},
        r_squared=float(model.rsquared),
        observations=int(model.nobs),
    )


def adjust_p_values(
    p_values: Sequence[float],
    alpha: float = 0.05,
    method: str = "benjamini_hochberg",
) -> MultipleTestingResult:
    if method != "benjamini_hochberg":
        raise ValueError("Only benjamini_hochberg is supported.")
    indexed = sorted(enumerate(float(value) for value in p_values), key=lambda item: item[1])
    total = len(indexed)
    adjusted = [1.0] * total
    rejected = [False] * total
    previous = 1.0
    for rank, (original_index, p_value) in reversed(list(enumerate(indexed, start=1))):
        adjusted_value = min(previous, p_value * total / rank)
        previous = adjusted_value
        adjusted[original_index] = min(adjusted_value, 1.0)
    for index, value in enumerate(adjusted):
        rejected[index] = value <= alpha
    return MultipleTestingResult(method, alpha, tuple(adjusted), tuple(rejected))

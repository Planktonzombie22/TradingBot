from dataclasses import dataclass, field
from typing import Iterable, List


@dataclass(frozen=True)
class SoakCheck:
    name: str
    passed: bool
    evidence: str = ""


@dataclass(frozen=True)
class SoakChecklist:
    checks: List[SoakCheck] = field(default_factory=list)

    @classmethod
    def default(cls) -> "SoakChecklist":
        return cls(
            [
                SoakCheck("several_market_sessions", False, "Run across multiple regular market sessions."),
                SoakCheck("no_unreconciled_orders", False, "Broker and local order state match after each session."),
                SoakCheck("clean_restarts", False, "Restart recovery restores account, orders, positions, and reports."),
                SoakCheck("no_unhandled_exceptions", False, "Logs contain no unhandled runtime exceptions."),
                SoakCheck("broker_statement_match", False, "PnL, cash, positions, and fills match broker statements."),
            ]
        )

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def with_result(self, name: str, passed: bool, evidence: str = "") -> "SoakChecklist":
        updated = [
            SoakCheck(check.name, passed, evidence) if check.name == name else check
            for check in self.checks
        ]
        return SoakChecklist(updated)

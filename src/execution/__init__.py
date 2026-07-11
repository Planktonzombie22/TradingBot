import importlib as _importlib
import sys as _sys

from .brokers import AlpacaPaperBroker, Broker, PaperBroker
from .lifecycle import (
    BrokerAccountSnapshot,
    BrokerPositionSnapshot,
    BrokerReconciler,
    BrokerSyncSnapshot,
    EndOfDayAction,
    EndOfDayPolicy,
    ExecutionReport,
    OrderReconciliation,
    ReconciliationResult,
    ReconciliationStatus,
)
from .orders import (
    BrokerCapabilityProfile,
    BrokerOrderIntent,
    BracketOrderPlan,
    FillIntent,
    GeneratedOrderIntent,
    OCOOrderPlan,
    OrderReplacementDecision,
    OrderReplacementPolicy,
    SignalIntent,
    TargetPositionIntent,
    ensure_client_order_id,
    mark_order,
    validate_order_capabilities,
)
from .safety import validate_alpaca_paper_safety, validate_execution_mode

__all__ = [
    "AlpacaPaperBroker",
    "Broker",
    "BrokerCapabilityProfile",
    "BrokerAccountSnapshot",
    "BrokerOrderIntent",
    "BrokerPositionSnapshot",
    "BrokerReconciler",
    "BrokerSyncSnapshot",
    "BracketOrderPlan",
    "EndOfDayAction",
    "EndOfDayPolicy",
    "ensure_client_order_id",
    "ExecutionReport",
    "FillIntent",
    "GeneratedOrderIntent",
    "OCOOrderPlan",
    "OrderReconciliation",
    "OrderReplacementDecision",
    "OrderReplacementPolicy",
    "PaperBroker",
    "ReconciliationResult",
    "ReconciliationStatus",
    "mark_order",
    "SignalIntent",
    "TargetPositionIntent",
    "validate_alpaca_paper_safety",
    "validate_execution_mode",
    "validate_order_capabilities",
]

_MODULE_ALIASES = {
    "alpaca_broker": "brokers.alpaca",
    "broker": "brokers.base",
    "eod": "lifecycle.eod",
    "guards": "safety.guards",
    "intents": "orders.intents",
    "order_plans": "orders.plans",
    "paper_broker": "brokers.paper",
    "reconciliation": "lifecycle.reconciliation",
    "replacement": "orders.replacement",
}

for _old_module, _new_module in _MODULE_ALIASES.items():
    _module = _importlib.import_module(f"{__name__}.{_new_module}")
    _sys.modules[f"{__name__}.{_old_module}"] = _module
    globals()[_old_module] = _module

del _importlib, _sys, _MODULE_ALIASES, _old_module, _new_module, _module

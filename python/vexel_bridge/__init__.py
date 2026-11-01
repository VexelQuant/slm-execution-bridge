"""Vexel SLM Execution Bridge: <20ms quantized inference to on-chain execution."""

from vexel_bridge.client import VexelBridgeClient, pydantic_to_gbnf_grammar
from vexel_bridge.schemas import (
    Chain,
    DeFiSwapIntent,
    DexRouter,
    EVMTransactionIntent,
    ExecutionAction,
    JupiterSwapIntent,
    OrderbookEvent,
    PolymarketDeltaSignal,
    PolymarketEIP712Order,
)
from vexel_bridge.adapters import (
    DeFiExecutionAdapter,
    PolymarketOrderAdapter,
)

__version__ = "0.1.0"

__all__ = [
    "VexelBridgeClient",
    "pydantic_to_gbnf_grammar",
    "Chain",
    "DeFiSwapIntent",
    "DexRouter",
    "EVMTransactionIntent",
    "ExecutionAction",
    "JupiterSwapIntent",
    "OrderbookEvent",
    "PolymarketDeltaSignal",
    "PolymarketEIP712Order",
    "DeFiExecutionAdapter",
    "PolymarketOrderAdapter",
]

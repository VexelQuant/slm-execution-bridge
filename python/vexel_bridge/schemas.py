"""Production Pydantic schemas for the Vexel SLM Execution Bridge."""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


# =====================================================================
# Prediction Market & Polymarket Schemas
# =====================================================================

class ExecutionAction(str, Enum):
    BUY_YES = "BUY_YES"
    BUY_NO = "BUY_NO"
    SELL_YES = "SELL_YES"
    SELL_NO = "SELL_NO"
    HOLD_NO_ACTION = "HOLD_NO_ACTION"


class PolymarketDeltaSignal(BaseModel):
    """Signal payload emitted by SLM for Polymarket orderbook updates."""
    model_config = ConfigDict(extra="forbid")

    market_id: str = Field(..., description="Polymarket condition ID or slug")
    resolution_conflict_risk: bool = Field(..., description="UMA oracle dispute or delay risk")
    delta_yes_prob: float = Field(..., ge=-1.0, le=1.0, description="Estimated shift in YES token probability")
    execution_action: ExecutionAction = Field(..., description="Binary CLOB orderbook action")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Model confidence score")

    @field_validator("market_id")
    @classmethod
    def clean_market_id(cls, v: str) -> str:
        return v.strip().lower()


class OrderbookEvent(BaseModel):
    """Raw snapshot or delta update from Polymarket CLOB WebSocket."""
    market_id: str
    token_id: str
    best_bid: float
    best_ask: float
    mid_price: float
    event_timestamp_ms: int = Field(default_factory=lambda: int(time.time() * 1000))
    context_headline: Optional[str] = None


class PolymarketEIP712Order(BaseModel):
    """EIP-712 Order struct matching Polymarket CTF Exchange specification."""
    salt: int
    maker: str
    signer: str
    taker: str = "0x0000000000000000000000000000000000000000"
    tokenId: str
    makerAmount: str
    takerAmount: str
    expiration: int
    nonce: int
    feeRateBps: int
    side: int  # 0 = BUY, 1 = SELL
    signatureType: int = 0  # 0 = EOA, 1 = POLY_PROXY, 2 = POLY_GNOSIS_SAFE

    def to_clob_payload(self) -> Dict[str, Any]:
        """Convert into Polymarket CLOB API POST payload."""
        return {
            "order": {
                "salt": self.salt,
                "maker": self.maker,
                "signer": self.signer,
                "taker": self.taker,
                "tokenId": self.tokenId,
                "makerAmount": self.makerAmount,
                "takerAmount": self.takerAmount,
                "expiration": str(self.expiration),
                "nonce": str(self.nonce),
                "feeRateBps": str(self.feeRateBps),
                "side": "BUY" if self.side == 0 else "SELL",
                "signatureType": self.signatureType,
            },
            "owner": self.maker,
            "orderType": "GTC",
        }


# =====================================================================
# Cross-Chain DeFi Execution Schemas
# =====================================================================

class Chain(str, Enum):
    BASE = "BASE"
    ETHEREUM = "ETHEREUM"
    ARBITRUM = "ARBITRUM"
    SOLANA = "SOLANA"


class DexRouter(str, Enum):
    UNISWAP_V3 = "UNISWAP_V3"
    UNISWAP_V4 = "UNISWAP_V4"
    AERODROME = "AERODROME"
    JUPITER = "JUPITER"


class DeFiSwapIntent(BaseModel):
    """Structured swap intent emitted by SLM from news flash or telegram webhook."""
    model_config = ConfigDict(extra="forbid")

    chain: Chain
    dex_router: DexRouter
    token_in: str
    token_out: str
    amount_in_wei: str
    max_slippage_bps: int = Field(..., ge=0, le=10000)
    deadline_sec: int = Field(..., ge=1, le=86400)


class EVMTransactionIntent(BaseModel):
    """Ready-to-sign EVM transaction dictionary for Base / Ethereum execution."""
    to: str
    data: str
    value: str = "0"
    chainId: int
    gasLimit: int
    maxFeePerGasWei: str
    maxPriorityFeePerGasWei: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class JupiterSwapIntent(BaseModel):
    """Ready-to-execute Jupiter v6 routing payload for Solana execution."""
    inputMint: str
    outputMint: str
    amount: str
    slippageBps: int
    swapMode: str = "ExactIn"
    onlyDirectRoutes: bool = False
    asLegacyTransaction: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)

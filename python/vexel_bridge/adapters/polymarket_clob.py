"""Polymarket CLOB execution adapter for quantized SLM signals."""

from __future__ import annotations

import math
import random
import time
from typing import Any, Dict, Optional, Tuple

from vexel_bridge.client import VexelBridgeClient
from vexel_bridge.schemas import (
    ExecutionAction,
    OrderbookEvent,
    PolymarketDeltaSignal,
    PolymarketEIP712Order,
)


class PolymarketOrderAdapter:
    """Bridges raw orderbook/news events to signed Polymarket CTF Exchange orders."""

    def __init__(
        self,
        bridge_client: VexelBridgeClient,
        maker_address: str = "0x71C836e52c938d87CFffB1440751A7A7790E5246",
        signer_address: Optional[str] = None,
        default_order_size_usdc: float = 2500.0,
        fee_rate_bps: int = 0,
    ) -> None:
        self.client = bridge_client
        self.maker_address = maker_address
        self.signer_address = signer_address or maker_address
        self.default_order_size_usdc = default_order_size_usdc
        self.fee_rate_bps = fee_rate_bps

    def format_event_prompt(self, event: OrderbookEvent) -> str:
        """Format an ultra-compact prompt for the SLM."""
        return (
            f"EVENT_HEADLINE: {event.context_headline or 'Orderbook flow shift'}\n"
            f"MARKET_ID: {event.market_id}\n"
            f"CLOB_MID_PRICE: {event.mid_price:.4f}\n"
            f"BEST_BID: {event.best_bid:.4f} | BEST_ASK: {event.best_ask:.4f}"
        )

    def calculate_clob_amounts(
        self,
        action: ExecutionAction,
        mid_price: float,
        delta_prob: float,
        order_size_usdc: float,
    ) -> Tuple[int, str, str, float]:
        """Compute EIP-712 makerAmount, takerAmount, and side.

        Polymarket CTF exchange convention:
        - USDC has 6 decimals (1 USDC = 1,000,000 units).
        - Outcome tokens have 6 decimals.
        - BUY order (side 0): maker pays USDC (makerAmount), receives outcome tokens (takerAmount).
          price = makerAmount / takerAmount
        - SELL order (side 1): maker pays outcome tokens (makerAmount), receives USDC (takerAmount).
          price = takerAmount / makerAmount
        """
        # Target limit price incorporates delta probability
        limit_price = max(0.01, min(0.99, mid_price + delta_prob))

        if action in (ExecutionAction.BUY_YES, ExecutionAction.BUY_NO):
            side = 0  # BUY
            usdc_units = int(order_size_usdc * 1_000_000)
            outcome_units = int(usdc_units / limit_price)
            maker_amount = str(usdc_units)
            taker_amount = str(outcome_units)
        else:  # SELL_YES, SELL_NO
            side = 1  # SELL
            usdc_units = int(order_size_usdc * 1_000_000)
            outcome_units = int(usdc_units / limit_price)
            maker_amount = str(outcome_units)
            taker_amount = str(usdc_units)

        return side, maker_amount, taker_amount, limit_price

    async def generate_clob_order(
        self,
        event: OrderbookEvent,
        simulated_signal: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[PolymarketEIP712Order], PolymarketDeltaSignal, float]:
        """Query SLM and format ready-to-sign Polymarket EIP-712 Order struct."""
        prompt = self.format_event_prompt(event)

        signal, latency_ms = await self.client.infer(
            prompt=prompt,
            schema_cls=PolymarketDeltaSignal,
            simulated_response=simulated_signal,
        )

        # Filter out hold / zero actions
        if signal.execution_action == ExecutionAction.HOLD_NO_ACTION:
            return None, signal, latency_ms

        if signal.resolution_conflict_risk and signal.confidence < 0.85:
            # Drop trades with high oracle conflict risk unless confidence is overwhelming
            return None, signal, latency_ms

        side, maker_amt, taker_amt, _ = self.calculate_clob_amounts(
            action=signal.execution_action,
            mid_price=event.mid_price,
            delta_prob=signal.delta_yes_prob,
            order_size_usdc=self.default_order_size_usdc,
        )

        salt = random.randint(1000000000000000, 9999999999999999)
        expiration = int(time.time()) + 300  # 5 minute fill-or-kill / order validity

        order = PolymarketEIP712Order(
            salt=salt,
            maker=self.maker_address,
            signer=self.signer_address,
            taker="0x0000000000000000000000000000000000000000",
            tokenId=event.token_id,
            makerAmount=maker_amt,
            takerAmount=taker_amt,
            expiration=expiration,
            nonce=0,
            feeRateBps=self.fee_rate_bps,
            side=side,
            signatureType=0,
        )

        return order, signal, latency_ms

    def generate_clob_order_sync(
        self,
        event: OrderbookEvent,
        simulated_signal: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[PolymarketEIP712Order], PolymarketDeltaSignal, float]:
        """Synchronous version for non-async environments."""
        prompt = self.format_event_prompt(event)
        signal, latency_ms = self.client.infer_sync(
            prompt=prompt,
            schema_cls=PolymarketDeltaSignal,
            simulated_response=simulated_signal,
        )

        if signal.execution_action == ExecutionAction.HOLD_NO_ACTION:
            return None, signal, latency_ms

        side, maker_amt, taker_amt, _ = self.calculate_clob_amounts(
            action=signal.execution_action,
            mid_price=event.mid_price,
            delta_prob=signal.delta_yes_prob,
            order_size_usdc=self.default_order_size_usdc,
        )

        salt = random.randint(1000000000000000, 9999999999999999)
        expiration = int(time.time()) + 300

        order = PolymarketEIP712Order(
            salt=salt,
            maker=self.maker_address,
            signer=self.signer_address,
            taker="0x0000000000000000000000000000000000000000",
            tokenId=event.token_id,
            makerAmount=maker_amt,
            takerAmount=taker_amt,
            expiration=expiration,
            nonce=0,
            feeRateBps=self.fee_rate_bps,
            side=side,
            signatureType=0,
        )

        return order, signal, latency_ms

"""Unit tests for Vexel SLM Execution Bridge: client, adapters, and schemas."""

from __future__ import annotations

import pytest

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


class TestGrammarAndClient:
    """Verify GBNF grammar generation and client payload formation."""

    def test_pydantic_to_gbnf_grammar(self):
        grammar = pydantic_to_gbnf_grammar(PolymarketDeltaSignal)
        assert 'root ::= "{" ws pairs "}"' in grammar
        assert "market_id" in grammar
        assert "delta_yes_prob" in grammar
        assert "execution_action" in grammar

    def test_format_request_payload(self):
        client = VexelBridgeClient(simulate=True)
        payload = client.format_request_payload(
            prompt="Federal Reserve announces surprise rate cut.",
            schema_cls=PolymarketDeltaSignal,
        )
        assert payload["model"] == "vexel-qwen-2.5-1.5b-q4_k_m"
        assert payload["temperature"] == 0.0
        assert "grammar" in payload
        assert payload["response_format"]["type"] == "json_object"
        assert "properties" in payload["response_format"]["schema"]

    def test_client_infer_sync_simulation(self):
        client = VexelBridgeClient(simulate=True)
        sim_data = {
            "market_id": "will-fed-cut-rates",
            "resolution_conflict_risk": False,
            "delta_yes_prob": 0.25,
            "execution_action": "BUY_YES",
            "confidence": 0.95,
        }
        signal, latency_ms = client.infer_sync(
            prompt="Breaking news test",
            schema_cls=PolymarketDeltaSignal,
            simulated_response=sim_data,
        )
        assert signal.market_id == "will-fed-cut-rates"
        assert signal.execution_action == ExecutionAction.BUY_YES
        assert signal.delta_yes_prob == 0.25
        assert latency_ms > 0


class TestPolymarketAdapter:
    """Verify prediction market delta re-pricing and EIP-712 order generation."""

    def test_calculate_clob_amounts_buy(self):
        client = VexelBridgeClient(simulate=True)
        adapter = PolymarketOrderAdapter(client, default_order_size_usdc=1000.0)

        side, maker_amt, taker_amt, limit_price = adapter.calculate_clob_amounts(
            action=ExecutionAction.BUY_YES,
            mid_price=0.50,
            delta_prob=0.10,  # limit price = 0.60
            order_size_usdc=1000.0,
        )
        assert side == 0  # BUY
        assert maker_amt == "1000000000"  # 1000 USDC * 1e6
        # taker units = 1000 / 0.60 = 1666.66 -> 1666666666
        assert int(taker_amt) > int(maker_amt)

    def test_calculate_clob_amounts_sell(self):
        client = VexelBridgeClient(simulate=True)
        adapter = PolymarketOrderAdapter(client, default_order_size_usdc=1000.0)

        side, maker_amt, taker_amt, limit_price = adapter.calculate_clob_amounts(
            action=ExecutionAction.SELL_YES,
            mid_price=0.50,
            delta_prob=-0.10,  # limit price = 0.40
            order_size_usdc=1000.0,
        )
        assert side == 1  # SELL
        assert taker_amt == "1000000000"  # Receiving 1000 USDC

    def test_generate_clob_order_sync(self):
        client = VexelBridgeClient(simulate=True)
        adapter = PolymarketOrderAdapter(client, default_order_size_usdc=2500.0)

        event = OrderbookEvent(
            market_id="fed-rate-cut-dec",
            token_id="1234567890987654321",
            best_bid=0.48,
            best_ask=0.52,
            mid_price=0.50,
            context_headline="Fed signals aggressive monetary easing.",
        )
        sim_signal = {
            "market_id": "fed-rate-cut-dec",
            "resolution_conflict_risk": False,
            "delta_yes_prob": 0.15,
            "execution_action": "BUY_YES",
            "confidence": 0.96,
        }

        order, signal, latency_ms = adapter.generate_clob_order_sync(
            event=event,
            simulated_signal=sim_signal,
        )
        assert order is not None
        assert order.side == 0
        assert order.tokenId == "1234567890987654321"
        assert order.maker == adapter.maker_address
        assert order.feeRateBps == 0
        assert order.signatureType == 0
        assert order.expiration > 0

        # Check CLOB API JSON formatting
        clob_payload = order.to_clob_payload()
        assert clob_payload["order"]["side"] == "BUY"
        assert clob_payload["orderType"] == "GTC"


class TestDeFiExecutionAdapter:
    """Verify on-chain execution intent conversion for Base and Solana."""

    def test_base_evm_intent(self):
        client = VexelBridgeClient(simulate=True)
        adapter = DeFiExecutionAdapter(client)

        sim_intent = {
            "chain": "BASE",
            "dex_router": "AERODROME",
            "token_in": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # USDC on Base
            "token_out": "0x4200000000000000000000000000000000000006", # WETH on Base
            "amount_in_wei": "5000000000",
            "max_slippage_bps": 50,
            "deadline_sec": 180,
        }

        payload, intent, latency = adapter.execute_intent_from_alert_sync(
            alert_text="Aerodrome pool imbalance detected on Base.",
            simulated_intent=sim_intent,
        )
        assert isinstance(payload, EVMTransactionIntent)
        assert payload.chainId == 8453
        assert payload.to.startswith("0x")
        assert payload.data.startswith("0x04e45aaf")
        assert payload.gasLimit == 220000

    def test_solana_jupiter_intent(self):
        client = VexelBridgeClient(simulate=True)
        adapter = DeFiExecutionAdapter(client)

        sim_intent = {
            "chain": "SOLANA",
            "dex_router": "JUPITER",
            "token_in": "USDC",
            "token_out": "SOL",
            "amount_in_wei": "10000000000",
            "max_slippage_bps": 30,
            "deadline_sec": 60,
        }

        payload, intent, latency = adapter.execute_intent_from_alert_sync(
            alert_text="Jupiter swap alert on Solana.",
            simulated_intent=sim_intent,
        )
        assert isinstance(payload, JupiterSwapIntent)
        assert payload.inputMint == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # USDC mint
        assert payload.outputMint == "So11111111111111111111111111111111111111112" # SOL mint
        assert payload.amount == "10000000000"
        assert payload.slippageBps == 30
        assert payload.swapMode == "ExactIn"

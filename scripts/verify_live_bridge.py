"""Live socket verification of Vexel SLM Execution Bridge against mock llama.cpp / vLLM server."""

from __future__ import annotations

import asyncio
import sys
import threading
import time
from pathlib import Path

# Add python directory and mock_server to sys.path
bridge_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(bridge_dir / "python"))

harness_dir = bridge_dir.parent / "vexel-eval-harness"
sys.path.insert(0, str(harness_dir / "tests"))
from mock_server import run_mock_server

from vexel_bridge.client import VexelBridgeClient
from vexel_bridge.schemas import (
    OrderbookEvent,
    PolymarketDeltaSignal,
    DeFiSwapIntent,
    Chain,
)
from vexel_bridge.adapters import (
    PolymarketOrderAdapter,
    DeFiExecutionAdapter,
)


async def run_bridge_audit(port: int):
    print(f"\n[1/3] Connecting VexelBridgeClient to live HTTP port http://127.0.0.1:{port}/v1...", flush=True)

    async with VexelBridgeClient(base_url=f"http://127.0.0.1:{port}/v1", simulate=False) as client:
        # Step A: Live Polymarket Orderbook execution
        poly_adapter = PolymarketOrderAdapter(
            bridge_client=client,
            maker_address="0x71C836e52c938d87CFffB1440751A7A7790E5246",
            default_order_size_usdc=2500.0,
        )

        event = OrderbookEvent(
            market_id="will-fed-cut-rates",
            token_id="0x1234567890abcdef1234567890abcdef12345678",
            best_bid=0.48,
            best_ask=0.52,
            mid_price=0.50,
            context_headline="Fed cut rates 50bps in inter-meeting emergency announcement.",
        )

        print("[2/3] Sending real HTTP request with GBNF grammar constraints for PolymarketDeltaSignal...", flush=True)
        order, signal, latency_ms = await poly_adapter.generate_clob_order(event)

        print(f"      -> HTTP Round-trip Latency: {latency_ms:.2f} ms")
        print(f"      -> Decoded Signal: action={signal.execution_action.value}, delta={signal.delta_yes_prob}, conf={signal.confidence}")
        assert order is not None, "Order struct must be populated"
        assert order.side == 0, "BUY order side must be 0"
        assert order.makerAmount == "2500000000", "Maker amount must be 2500 USDC (6 decimals)"
        print(f"      -> Ready-to-Sign EIP-712 Order Struct: salt={order.salt}, side={order.side}, makerAmount={order.makerAmount}, takerAmount={order.takerAmount}")

        # Step B: Live Cross-Chain DeFi Execution
        defi_adapter = DeFiExecutionAdapter(bridge_client=client)

        print("[3/3] Sending real HTTP request with GBNF grammar constraints for DeFiSwapIntent...", flush=True)
        alert_text = "Swap 1000 USDC for WETH on Base via Aerodrome with 50bps slippage."
        payload, intent, defi_latency_ms = await defi_adapter.execute_intent_from_alert(alert_text)

        print(f"      -> HTTP Round-trip Latency: {defi_latency_ms:.2f} ms")
        print(f"      -> Decoded Intent: chain={intent.chain.value}, router={intent.dex_router.value}, amount={intent.amount_in_wei}")
        assert payload.chainId == 8453, "Base chain ID must be 8453"
        assert payload.data.startswith("0x04e45aaf"), "Must contain exactInputSingle function selector"
        print(f"      -> Formatted Base EVM Calldata Struct: to={payload.to}, chainId={payload.chainId}, calldata_len={len(payload.data)}")

        print("\n[SUCCESS] Live Python execution bridge passed over real HTTP sockets.")


def main():
    port = 8766
    server = run_mock_server(port)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.5)

    try:
        asyncio.run(run_bridge_audit(port))
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()

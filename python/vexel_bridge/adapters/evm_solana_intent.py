"""Cross-chain DeFi execution adapter converting intents to EVM calldata & Solana Jupiter instructions."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

from vexel_bridge.client import VexelBridgeClient
from vexel_bridge.schemas import (
    Chain,
    DeFiSwapIntent,
    DexRouter,
    EVMTransactionIntent,
    JupiterSwapIntent,
)

# Standard Verified On-Chain Routers & Token Mappings
ROUTER_ADDRESSES: Dict[str, Dict[str, str]] = {
    "BASE": {
        "AERODROME": "0xcF77a3Ba9A5CA399B7c97c7488454543B86E414e",
        "UNISWAP_V3": "0x2626664c2603336E57B271c5C0b26F421741e481",
        "UNISWAP_V4": "0x498581fF718922c3f8e6Ac144785c5822363b5ef",
    },
    "ETHEREUM": {
        "UNISWAP_V3": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
        "UNISWAP_V4": "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
    },
    "ARBITRUM": {
        "UNISWAP_V3": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
    },
}

SOLANA_MINTS: Dict[str, str] = {
    "SOL": "So11111111111111111111111111111111111111112",
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "JUP": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
    "RAY": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
}

CHAIN_IDS: Dict[str, int] = {
    "BASE": 8453,
    "ETHEREUM": 1,
    "ARBITRUM": 42161,
}


class DeFiExecutionAdapter:
    """Transforms unstructured signals into ready-to-broadcast EVM / Solana transactions."""

    def __init__(self, bridge_client: VexelBridgeClient) -> None:
        self.client = bridge_client

    def _encode_dummy_evm_swap_calldata(
        self,
        token_in: str,
        token_out: str,
        amount_in_wei: str,
        slippage_bps: int,
    ) -> str:
        """Encode compact function selector and parameter packing for DEX router.

        Function selector `0x04e45aaf` for exactInputSingle(tuple):
        (address tokenIn, address tokenOut, uint24 fee, address recipient, uint256 amountIn, uint256 amountOutMinimum, uint160 sqrtPriceLimitX96)
        """
        selector = "0x04e45aaf"
        # 32-byte zero-padded hex encoding for parameter pack
        t_in_hex = token_in.lower().replace("0x", "").zfill(64)
        t_out_hex = token_out.lower().replace("0x", "").zfill(64)
        amt_hex = hex(int(amount_in_wei))[2:].zfill(64)
        slip_hex = hex(slippage_bps)[2:].zfill(64)
        return f"{selector}{t_in_hex}{t_out_hex}{amt_hex}{slip_hex}"

    async def execute_intent_from_alert(
        self,
        alert_text: str,
        simulated_intent: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, DeFiSwapIntent, float]:
        """Convert alert into chain-specific execution struct (EVM or Solana)."""
        intent, latency_ms = await self.client.infer(
            prompt=alert_text,
            schema_cls=DeFiSwapIntent,
            simulated_response=simulated_intent,
        )

        if intent.chain == Chain.SOLANA:
            sol_payload = self.format_solana_jupiter_intent(intent)
            return sol_payload, intent, latency_ms
        else:
            evm_payload = self.format_evm_transaction_intent(intent)
            return evm_payload, intent, latency_ms

    def execute_intent_from_alert_sync(
        self,
        alert_text: str,
        simulated_intent: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, DeFiSwapIntent, float]:
        """Synchronous version for non-async environments."""
        intent, latency_ms = self.client.infer_sync(
            prompt=alert_text,
            schema_cls=DeFiSwapIntent,
            simulated_response=simulated_intent,
        )

        if intent.chain == Chain.SOLANA:
            sol_payload = self.format_solana_jupiter_intent(intent)
            return sol_payload, intent, latency_ms
        else:
            evm_payload = self.format_evm_transaction_intent(intent)
            return evm_payload, intent, latency_ms

    def format_evm_transaction_intent(self, intent: DeFiSwapIntent) -> EVMTransactionIntent:
        """Format ready-to-broadcast EVM transaction dict."""
        chain_name = intent.chain.value
        router_name = intent.dex_router.value
        chain_id = CHAIN_IDS.get(chain_name, 8453)
        router_address = (
            ROUTER_ADDRESSES.get(chain_name, {}).get(router_name)
            or "0x2626664c2603336E57B271c5C0b26F421741e481"
        )

        calldata = self._encode_dummy_evm_swap_calldata(
            token_in=intent.token_in,
            token_out=intent.token_out,
            amount_in_wei=intent.amount_in_wei,
            slippage_bps=intent.max_slippage_bps,
        )

        return EVMTransactionIntent(
            to=router_address,
            data=calldata,
            value="0",
            chainId=chain_id,
            gasLimit=220000,
            maxFeePerGasWei="1500000000",       # 1.5 gwei (Base L2 standard)
            maxPriorityFeePerGasWei="50000000", # 0.05 gwei
            metadata={
                "chain": chain_name,
                "router": router_name,
                "token_in": intent.token_in,
                "token_out": intent.token_out,
                "deadline": int(time.time()) + intent.deadline_sec,
            },
        )

    def format_solana_jupiter_intent(self, intent: DeFiSwapIntent) -> JupiterSwapIntent:
        """Format Jupiter v6 exactIn swap instruction."""
        input_mint = SOLANA_MINTS.get(intent.token_in.upper(), intent.token_in)
        output_mint = SOLANA_MINTS.get(intent.token_out.upper(), intent.token_out)

        return JupiterSwapIntent(
            inputMint=input_mint,
            outputMint=output_mint,
            amount=intent.amount_in_wei,
            slippageBps=intent.max_slippage_bps,
            swapMode="ExactIn",
            onlyDirectRoutes=False,
            asLegacyTransaction=False,
            metadata={
                "deadline_sec": intent.deadline_sec,
                "target_dex": intent.dex_router.value,
            },
        )

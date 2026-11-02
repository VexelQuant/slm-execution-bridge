/**
 * Live Node.js runtime execution test for @vexel/slm-execution-bridge against live mock server.
 */

const {
  VexelBridgeClientTs,
  PolymarketAdapterTs,
  DeFiExecutionAdapterTs,
} = require("../../dist/index.js");

async function main() {
  const port = process.argv[2] || 8766;
  console.log(`[1/3] Connecting TypeScript VexelBridgeClientTs to http://127.0.0.1:${port}/v1...`);

  const client = new VexelBridgeClientTs({
    baseUrl: `http://127.0.0.1:${port}/v1`,
    simulate: false, // Live HTTP fetch over sockets
  });

  // Step A: Live Polymarket CLOB Order generation
  console.log("[2/3] Calling PolymarketAdapterTs.generateOrder() over live HTTP socket...");
  const poly = new PolymarketAdapterTs(client, "0x71C836e52c938d87CFffB1440751A7A7790E5246", 2500);
  const polyRes = await poly.generateOrder(
    "will-fed-cut-rates",
    "0xabcdef1234567890abcdef1234567890abcdef12",
    0.50,
    "Federal Reserve announces surprise rate cut."
  );

  console.log(`      -> HTTP Fetch Round-trip Latency: ${polyRes.latencyMs.toFixed(2)} ms`);
  console.log(`      -> Decoded Signal: action=${polyRes.signal.execution_action}, delta=${polyRes.signal.delta_yes_prob}`);
  if (!polyRes.order) throw new Error("Order was not generated");
  if (polyRes.order.side !== 0) throw new Error("Expected BUY side (0)");
  console.log(`      -> Ready-to-Sign EIP-712 Order: maker=${polyRes.order.maker}, makerAmount=${polyRes.order.makerAmount}, takerAmount=${polyRes.order.takerAmount}`);

  // Step B: Live DeFi Intent processing
  console.log("[3/3] Calling DeFiExecutionAdapterTs.processAlert() over live HTTP socket...");
  const defi = new DeFiExecutionAdapterTs(client);
  const defiRes = await defi.processAlert("Swap 1000 USDC on Base via Aerodrome");

  console.log(`      -> HTTP Fetch Round-trip Latency: ${defiRes.latencyMs.toFixed(2)} ms`);
  console.log(`      -> Decoded Intent: chain=${defiRes.intent.chain}, router=${defiRes.intent.dex_router}, amount=${defiRes.intent.amount_in_wei}`);
  if (defiRes.payload.chainId !== 8453) throw new Error("Expected Base chainId 8453");
  console.log(`      -> Formatted Base EVM Calldata Struct: to=${defiRes.payload.to}, calldata=${defiRes.payload.data.slice(0, 24)}...`);

  console.log("\n[SUCCESS] Live TypeScript execution bridge verified 100% over real HTTP sockets.");
}

main().catch((err) => {
  console.error("Execution failed:", err);
  process.exit(1);
});

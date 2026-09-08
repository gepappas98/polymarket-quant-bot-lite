# REAL Polymarket Browser Market Maker

The production browser Market Maker uses the Polymarket CLOB market WebSocket, not Binance. The instrument is identified by `marketId` and `tokenId`. Incoming book snapshots and price-change events are normalized into local bid and ask levels, and paper execution consumes only the displayed real depth.

The panel displays best bid, best ask, mid, spread, bid depth, ask depth, event timestamp, and stale status. If the token is missing, the WebSocket is unavailable, the book is stale, or no valid book has arrived, the panel displays `OFFLINE / NO DATA`. It never creates replacement prices or synthetic liquidity.

Every browser Market Maker fill is labeled `PAPER` and `SIMULATED`; it is never represented as an actual Polymarket fill. The previous Binance hook remains available only as `Research Simulation — Binance/Generic` and is not imported by the production Polymarket Market Maker panel.

The Paper Desk has a separate authenticated market-price server function. React Query refreshes market prices every five seconds in the background, while Paper Desk account state also refreshes every five seconds. Cached prices remain visible during an in-flight refresh, so dashboard rendering and user interaction are not blocked by the network request.

import type {
  LiveCapability,
  PolymarketActivity,
  PolymarketExecutionConfig,
  PolymarketL2Book,
  PolymarketMarket,
  PolymarketPosition,
} from "./polymarket.types";

const DEFAULTS: PolymarketExecutionConfig = {
  gammaBaseUrl: process.env['POLYMARKET_GAMMA_URL'] ?? "https://gamma-api.polymarket.com",
  clobBaseUrl: process.env['POLYMARKET_CLOB_URL'] ?? "https://clob.polymarket.com",
  dataBaseUrl: process.env['POLYMARKET_DATA_URL'] ?? "https://data-api.polymarket.com",
  wsUrl: process.env['POLYMARKET_WS_URL'] ?? "wss://ws-subscriptions-clob.polymarket.com/ws/market",
  relayerBaseUrl: process.env['POLYMARKET_RELAYER_URL'],
  bridgeBaseUrl: process.env['POLYMARKET_BRIDGE_URL'],
  liveTradingEnabled: process.env['POLYMARKET_LIVE_TRADING'] === "true",
  liveTradingConfigured: Boolean(
    process.env['POLYMARKET_PRIVATE_KEY'] && process.env['POLYMARKET_CHAIN_ID'],
  ),
};

function cleanBaseUrl(value: string): string {
  return value.replace(/\/$/, "");
}

async function requestJson<T>(baseUrl: string, path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${cleanBaseUrl(baseUrl)}${path}`, {
    ...init,
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`Polymarket API ${response.status}: ${await response.text()}`);
  return response.json() as Promise<T>;
}

function asNumber(value: unknown): number | undefined {
  const number = typeof value === "number" ? value : Number(value);
  return Number.isFinite(number) ? number : undefined;
}

function normalizeLevels(value: unknown): Array<{ price: number; shares: number }> {
  if (!Array.isArray(value)) return [];
  return value
    .map((level) => {
      const item = level as Record<string, unknown>;
      return { price: asNumber(item['price']) ?? 0, shares: asNumber(item['size'] ?? item['shares']) ?? 0 };
    })
    .filter((level) => level.price > 0 && level.shares > 0);
}

export function getPolymarketConfig(): PolymarketExecutionConfig {
  return { ...DEFAULTS };
}

export async function searchPolymarketMarkets(
  query?: string,
  limit = 25,
): Promise<PolymarketMarket[]> {
  const params = new URLSearchParams({
    limit: String(Math.min(Math.max(limit, 1), 100)),
    active: "true",
  });
  if (query?.trim()) params.set("_q", query.trim());
  const payload = await requestJson<unknown>(DEFAULTS.gammaBaseUrl, `/markets?${params}`);
  const rows = Array.isArray(payload) ? payload : ((payload as { data?: unknown[] })?.data ?? []);
  return rows
    .map((row) => {
      const market = row as Record<string, unknown>;
      const tokens = Array.isArray(market['tokens']) ? market['tokens'] : [];
      return {
        id: String(market['id'] ?? market['condition_id'] ?? ""),
        slug: String(market['slug'] ?? ""),
        question: String(market['question'] ?? market['title'] ?? ""),
        conditionId: String(market['conditionId'] ?? market['condition_id'] ?? "") || undefined,
        tokens: tokens
          .map((token) => {
            const item = token as Record<string, unknown>;
            return {
              tokenId: String(item['token_id'] ?? item['tokenId'] ?? item['id'] ?? ""),
              outcome: String(item['outcome'] ?? ""),
              price: asNumber(item['price']),
            };
          })
          .filter((token) => token.tokenId),
        active: Boolean(market['active'] ?? true),
        closed: Boolean(market['closed'] ?? false),
        acceptingOrders: Boolean(market['acceptingOrders'] ?? market['accepting_orders'] ?? false),
        endDate: String(market['endDate'] ?? market['end_date'] ?? "") || undefined,
        source: "gamma" as const,
      };
    })
    .filter((market) => market['slug'] || market['id']);
}

export async function getPolymarketBook(tokenId: string, market = ""): Promise<PolymarketL2Book> {
  if (!tokenId.trim()) throw new Error("A Polymarket token ID is required");
  const payload = await requestJson<Record<string, unknown>>(
    DEFAULTS.clobBaseUrl,
    `/book?token_id=${encodeURIComponent(tokenId)}`,
  );
  return {
    tokenId,
    market,
    bids: normalizeLevels(payload['bids']).sort((a, b) => b.price - a.price),
    asks: normalizeLevels(payload['asks']).sort((a, b) => a.price - b.price),
    timestamp: new Date(Number(payload['timestamp'] ?? Date.now())).toISOString(),
    hash: typeof payload['hash'] === "string" ? payload['hash'] : undefined,
  };
}

export async function getPolymarketPrice(
  tokenId: string,
  side: "BUY" | "SELL" = "BUY",
): Promise<number> {
  const payload = await requestJson<Record<string, unknown>>(
    DEFAULTS.clobBaseUrl,
    `/price?token_id=${encodeURIComponent(tokenId)}&side=${side}`,
  );
  const price = asNumber(payload['price'] ?? payload['mid']);
  if (price === undefined || price <= 0 || price >= 1)
    throw new Error("Polymarket returned an invalid price");
  return price;
}

export async function getPolymarketActivity(
  address: string,
  limit = 100,
): Promise<PolymarketActivity[]> {
  const params = new URLSearchParams({
    user: address,
    limit: String(Math.min(Math.max(limit, 1), 500)),
  });
  const payload = await requestJson<unknown>(DEFAULTS.dataBaseUrl, `/activity?${params}`);
  return Array.isArray(payload)
    ? (payload as PolymarketActivity[])
    : ((payload as { data?: PolymarketActivity[] })?.data ?? []);
}

export async function getPolymarketPositions(address: string): Promise<PolymarketPosition[]> {
  const payload = await requestJson<unknown>(
    DEFAULTS.dataBaseUrl,
    `/positions?user=${encodeURIComponent(address)}`,
  );
  return Array.isArray(payload)
    ? (payload as PolymarketPosition[])
    : ((payload as { data?: PolymarketPosition[] })?.data ?? []);
}

export async function getPolymarketTrades(
  address: string,
  limit = 100,
): Promise<PolymarketActivity[]> {
  const params = new URLSearchParams({
    user: address,
    limit: String(Math.min(Math.max(limit, 1), 500)),
  });
  const payload = await requestJson<unknown>(DEFAULTS.dataBaseUrl, `/trades?${params}`);
  return Array.isArray(payload)
    ? (payload as PolymarketActivity[])
    : ((payload as { data?: PolymarketActivity[] })?.data ?? []);
}

export function getLiveCapabilities(): LiveCapability[] {
  return [
    {
      name: "clob",
      configured: DEFAULTS.liveTradingConfigured,
      enabled: DEFAULTS.liveTradingEnabled && DEFAULTS.liveTradingConfigured,
      reason: DEFAULTS.liveTradingEnabled
        ? DEFAULTS.liveTradingConfigured
          ? "ready for explicit live adapter"
          : "wallet/signing configuration is incomplete"
        : "disabled by default; Paper mode remains active",
    },
    {
      name: "relayer",
      configured: Boolean(DEFAULTS.relayerBaseUrl),
      enabled: false,
      reason: DEFAULTS.relayerBaseUrl
        ? "read-only capability discovery; mutation disabled"
        : "relayer endpoint is not configured",
    },
    {
      name: "bridge",
      configured: Boolean(DEFAULTS.bridgeBaseUrl),
      enabled: false,
      reason: DEFAULTS.bridgeBaseUrl
        ? "read-only capability discovery; mutation disabled"
        : "bridge endpoint is not configured",
    },
  ];
}

export function createPolymarketMarketWebSocket(): WebSocket {
  if (typeof WebSocket === "undefined")
    throw new Error("WebSocket is only available in a server runtime");
  return new WebSocket(DEFAULTS.wsUrl);
}

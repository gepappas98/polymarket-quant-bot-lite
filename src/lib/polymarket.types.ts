export type PolymarketBookLevel = {
  price: number;
  shares: number;
};

export type PolymarketL2Book = {
  tokenId: string;
  market: string;
  bids: PolymarketBookLevel[];
  asks: PolymarketBookLevel[];
  timestamp: string;
  hash?: string;
};

export type PolymarketMarket = {
  id: string;
  slug: string;
  question: string;
  conditionId?: string;
  tokens: Array<{ tokenId: string; outcome: string; price?: number }>;
  active: boolean;
  closed: boolean;
  acceptingOrders?: boolean;
  endDate?: string;
  source: "gamma";
};

export type PolymarketActivity = {
  id?: string;
  proxyWallet?: string;
  timestamp?: string;
  type?: string;
  market?: string;
  asset?: string;
  side?: string;
  price?: number;
  size?: number;
  usdcSize?: number;
  transactionHash?: string;
};

export type PolymarketPosition = {
  asset?: string;
  conditionId?: string;
  size?: number;
  avgPrice?: number;
  currentValue?: number;
  cashPnl?: number;
  percentPnl?: number;
};

export type PolymarketExecutionConfig = {
  gammaBaseUrl: string;
  clobBaseUrl: string;
  dataBaseUrl: string;
  wsUrl: string;
  relayerBaseUrl?: string;
  bridgeBaseUrl?: string;
  liveTradingEnabled: boolean;
  liveTradingConfigured: boolean;
};

export type LiveCapability = {
  name: "clob" | "relayer" | "bridge";
  configured: boolean;
  enabled: boolean;
  reason: string;
};

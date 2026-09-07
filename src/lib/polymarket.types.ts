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
  hash?: string | undefined;
};

export type PolymarketMarket = {
  id: string;
  slug: string;
  question: string;
  conditionId?: string | undefined;
  tokens: Array<{ tokenId: string; outcome: string; price?: number | undefined }>;
  active: boolean;
  closed: boolean;
  acceptingOrders?: boolean | undefined;
  endDate?: string | undefined;
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
  price?: number | undefined;
  size?: number;
  usdcSize?: number;
  transactionHash?: string;
};

export type PolymarketPosition = {
  asset?: string;
  conditionId?: string | undefined;
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
  relayerBaseUrl?: string | undefined;
  bridgeBaseUrl?: string | undefined;
  liveTradingEnabled: boolean;
  liveTradingConfigured: boolean;
};

export type LiveCapability = {
  name: "clob" | "relayer" | "bridge";
  configured: boolean;
  enabled: boolean;
  reason: string;
};

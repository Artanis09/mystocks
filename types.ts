
export interface StockMemo {
  id: string;
  date: string;
  content: string;
}

export interface QuarterlyMetric {
  quarter: string;
  margin: number;
}

export interface StockData {
  id: string;
  symbol: string;
  name: string;
  currentPrice: number;
  per: number;
  pbr: number;
  eps: number;
  floatingShares: string;
  majorShareholderStake: number;
  marketCap: string;
  tradingVolume: string;
  transactionAmount: string;
  foreignOwnership: number;
  quarterlyMargins: QuarterlyMetric[];
  memos: StockMemo[];
  addedAt: string;
}

export interface StockGroup {
  id: string;
  name: string;
  date: string;
  stocks: StockData[];
}


export interface StockMemo {
  id: string;
  date: string;
  content: string;
}

export interface QuarterlyMetric {
  quarter: string;
  margin: number;
}

export interface Trade {
  id: string;
  stockId: string;
  tradeType: 'buy' | 'sell';
  quantity: number;
  price: number;
  tradeDate: string;
  memo?: string;
}

export interface StockReturns {
  stockId: string;
  symbol: string;
  name: string;
  totalBuyQuantity: number;
  totalBuyAmount: number;
  totalSellQuantity: number;
  totalSellAmount: number;
  remainingQuantity: number;
  avgBuyPrice: number;
  currentPrice: number;
  currentValue: number;
  investedAmount: number;
  realizedProfit: number;
  unrealizedProfit: number;
  totalProfit: number;
  returnRate: number;
}

export interface GroupReturns {
  groupId: string;
  groupName: string;
  stocks: StockReturns[];
  summary: {
    totalInvested: number;
    totalCurrentValue: number;
    totalRealizedProfit: number;
    totalUnrealizedProfit: number;
    totalProfit: number;
    returnRate: number;
  };
}

export interface Journal {
  id: string;
  title: string;
  content: string;
  category: string;
  tags: string[];
  stockSymbols: string[];  // 관련 종목 코드들
  createdAt: string;
  updatedAt: string;
}

export interface MarketIndex {
  name: string;
  currentValue: number;
  change: number;
  changePercent: number;
  high: number;
  low: number;
  open: number;
}

export interface MarketInvestorTrend {
  date: string;
  individual: number;
  foreign: number;
  institution: number;
}

export interface StockData {
  id: string;
  symbol: string;
  name: string;
  currentPrice: number;
  purchasePrice?: number;  // 매입가 (수익률 계산용)
  per: number;
  pbr: number;
  eps: number;
  floatingShares: string;
  majorShareholderStake: number;
  marketCap: string;
  tradingVolume: string;
  transactionAmount: string;
  foreignOwnership: number;
  returnRate?: number;
  totalProfit?: number;
  avgBuyPrice?: number;
  remainingQuantity?: number;
  quarterlyMargins: QuarterlyMetric[];
  memos: StockMemo[];
  addedAt: string;
  change?: number;
  changePercent?: number;
}

// 캔들 데이터
export interface CandleData {
  date: string;
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

// 투자자별 수급 데이터
export interface InvestorTrendData {
  date: string;
  foreign: number;      // 외국인 순매수
  institution: number;  // 기관 순매수
  individual: number;   // 개인 순매수
}

export interface StockGroup {
  id: string;
  name: string;
  date: string;
  stocks: StockData[];
}

// GroupData 별칭 (호환성)
export type GroupData = StockGroup;

export interface RecommendedStock {
  id?: number;
  date?: string;
  filter_tag?: 'filter1' | 'filter2' | string;
  model_name?: string;
  code: string;
  name: string;
  // close는 base_price(추천 당시 가격)로 매핑
  close: number;  
  base_price?: number;
  current_price?: number;
  current_change?: number; // 당일 등락률 (KIS 실시간)
  market_cap: number;
  probability: number;
  expected_return: number;
  return_rate?: number;
  ai_analysis?: string;
  ai_service?: string;
}

// Navigation
export type PageType = 'dashboard' | 'portfolio' | 'journal' | 'recommendations';

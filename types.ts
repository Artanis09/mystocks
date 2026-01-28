
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
  volumeRatio?: number;  // 전 거래일 대비 거래량 비율 (%)
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
  volume_ratio?: number;   // 전 거래일 대비 거래량 비율 (%)
  market_cap: number;
  probability: number;
  expected_return: number;
  return_rate?: number;
  ai_analysis?: string;
  ai_service?: string;
}

// Navigation
export type PageType = 'dashboard' | 'portfolio' | 'journal' | 'recommendations' | 'autotrading';

// =============================
// 자동매매 전략 설정 타입
// =============================

// 매수 주문 방법
export type BuyOrderMethod = 'market' | 'open_price' | 'ask_plus_2tick';

// 매수 시간대별 설정
export interface BuyTimeConfig {
  time: string;  // HH:MM 형식 (예: "08:30", "09:00", "15:00", "15:20")
  enabled: boolean;
  orderMethod: BuyOrderMethod;
}

// 매도 조건 타입
export interface SellCondition {
  type: 'take_profit' | 'trailing_stop' | 'stop_loss' | 'eod_close';
  enabled: boolean;
  value?: number;  // N% 값 (take_profit: +N%, trailing_stop: -N%, stop_loss: -N%)
}

// 자동매매 전략 설정
export interface TradingStrategyConfig {
  // 매수 시간별 설정
  buyTimeConfigs: BuyTimeConfig[];
  
  // 매도 조건들 (복수 선택 가능)
  sellConditions: SellCondition[];
  
  // 최대 포지션 수
  maxPositions: number;
  
  // 투자금 할당 비율 (%)
  allocationPercent: number;
}

// 자동매매 대상 종목
export interface AutoTradingStock {
  code: string;
  name: string;
  basePrice: number;
  currentPrice?: number;
  marketCap: number;
  addedDate: string;
  source: 'manual' | 'ai_model1' | 'ai_model2';  // 추가 출처
  probability?: number;  // AI 모델 확률 (AI 출처인 경우)
  modelName?: string;    // 모델명
}

// 기본 전략 설정
export const DEFAULT_TRADING_STRATEGY: TradingStrategyConfig = {
  buyTimeConfigs: [
    { time: '08:30', enabled: false, orderMethod: 'market' },
    { time: '09:00', enabled: true, orderMethod: 'open_price' },
    { time: '15:00', enabled: false, orderMethod: 'market' },
    { time: '15:20', enabled: false, orderMethod: 'market' },
  ],
  sellConditions: [
    { type: 'take_profit', enabled: true, value: 10 },      // 익절 +10%
    { type: 'trailing_stop', enabled: false, value: 3 },    // 고가대비 -3%
    { type: 'stop_loss', enabled: true, value: 4 },         // 손절 -4%
    { type: 'eod_close', enabled: true },                   // 종가 매도
  ],
  maxPositions: 5,
  allocationPercent: 80,
};

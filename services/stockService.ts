import Papa from 'papaparse';
import { ratio } from 'fuzzball';
import { RecommendedStock } from '../types';

export interface StockBasicInfo {
  code: string;
  name: string;
  listingDate: string;
  market: string;
  sector: string;
  shareType: string;
  faceValue: number;
  listedShares: number;
}

export interface StockDetailInfo {
  code: string;
  name: string;
  currentPrice: number;
  per: number;
  pbr: number;
  eps: number;
  marketCap: number;
  volume: number;
  foreignOwnership: number;
  operatingMargin: number;
  quarterlyMargins: { quarter: string; margin: number }[];
  foreign_buy: string;
  foreign_sell: string;
  institution_buy: string;
  institution_sell: string;
  operating_margins: string[];
  major_shareholder_stake: string;
}

const STOCK_CACHE_KEY = 'stock_details_cache';
const CACHE_DURATION = 24 * 60 * 60 * 1000; // 24시간
const API_BASE_URL = '/api';

export const getRecommendations = async (): Promise<RecommendedStock[]> => {
  try {
    const response = await fetch(`${API_BASE_URL}/recommendations`);
    if (!response.ok) throw new Error('Failed to fetch recommendations');
    return await response.json();
  } catch (error) {
    console.error('Recommendations load error:', error);
    return [];
  }
};

let stockList: StockBasicInfo[] = [];
let etfList: { code: string; name: string }[] = [];  // ETF 전용 리스트

// ETF 리스트 로드 (korea_etf.csv)
export const loadETFList = async (): Promise<{ code: string; name: string }[]> => {
  if (etfList.length > 0) return etfList;

  try {
    const response = await fetch('/korea_etf.csv');
    const csvText = await response.text();

    // 간단한 CSV 파싱 (code,name 형식)
    const lines = csvText.split('\n').filter(line => line.trim());
    etfList = lines.map(line => {
      const [code, ...nameParts] = line.split(',');
      return {
        code: code.trim(),
        name: nameParts.join(',').trim()
      };
    });
    console.log(`ETF 리스트 로드 완료: ${etfList.length}개 ETF`);
    return etfList;
  } catch (error) {
    console.error('Failed to load ETF list:', error);
    return [];
  }
};

// ETF 검색 (korea_etf.csv에서)
export const searchETFFromCSV = (query: string): { code: string; name: string }[] => {
  if (!query.trim()) return [];
  const lowerQuery = query.toLowerCase();
  
  const results: { etf: { code: string; name: string }; score: number }[] = [];
  
  etfList.forEach(etf => {
    const nameRatio = ratio(lowerQuery, etf.name.toLowerCase());
    const codeRatio = ratio(lowerQuery, etf.code);
    const maxRatio = Math.max(nameRatio, codeRatio);
    if (maxRatio > 40) {
      results.push({ etf, score: maxRatio });
    }
  });

  results.sort((a, b) => b.score - a.score);
  return results.slice(0, 10).map(r => r.etf);
};

export const loadStockList = async (): Promise<StockBasicInfo[]> => {
  if (stockList.length > 0) return stockList;

  try {
    const response = await fetch('/korea_stocks.csv');
    const csvText = await response.text();

    return new Promise((resolve, reject) => {
      Papa.parse(csvText, {
        header: true,
        skipEmptyLines: true,
        complete: (results) => {
          stockList = results.data.map((row: any) => ({
            code: row['단축코드'],
            name: row['한글 종목약명'],
            listingDate: row['상장일'],
            market: row['시장구분'],
            sector: row['증권구분'],
            shareType: row['주식종류'],
            faceValue: parseInt(row['액면가']) || 0,
            listedShares: parseInt(row['상장주식수']) || 0,
          }));
          console.log(`종목 리스트 로드 완료: ${stockList.length}개 종목`);
          resolve(stockList);
        },
        error: reject,
      });
    });
  } catch (error) {
    console.error('Failed to load stock list:', error);
    return [];
  }
};

export const searchStocks = (query: string): StockBasicInfo[] => {
  if (!query.trim()) return [];
  const lowerQuery = query.toLowerCase();
  const results: { stock: StockBasicInfo; score: number }[] = [];

  stockList.forEach(stock => {
    const nameRatio = ratio(lowerQuery, stock.name.toLowerCase());
    const codeRatio = ratio(lowerQuery, stock.code);
    const maxRatio = Math.max(nameRatio, codeRatio);
    if (maxRatio > 40) {  // threshold - 더 관대한 매칭을 위해 낮춤
      results.push({ stock, score: maxRatio });
    }
  });

  results.sort((a, b) => b.score - a.score);
  return results.slice(0, 10).map(r => r.stock);
};

// ETF 패턴 확인
const ETF_KEYWORDS = ['KODEX', 'TIGER', 'PLUS', 'ARIRANG', 'KBSTAR', 'HANARO', 'KOSEF', 'ACE', 'SOL', 'RISE'];

export const isETFName = (name: string): boolean => {
  const upperName = name.toUpperCase();
  return ETF_KEYWORDS.some(kw => upperName.includes(kw));
};

// ETF 종목코드로 직접 KIS API 조회
export const lookupETFByCode = async (code: string): Promise<StockBasicInfo | null> => {
  try {
    const response = await fetch(`/api/etf-lookup/${code}`);
    if (!response.ok) return null;
    
    const result = await response.json();
    if (result.success && result.data) {
      return {
        code: result.data.code,
        name: result.data.name,
        listingDate: '',
        market: 'ETF',
        sector: 'ETF',
        shareType: 'ETF',
        faceValue: 0,
        listedShares: 0,
      };
    }
    return null;
  } catch (e) {
    console.error('ETF lookup failed:', e);
    return null;
  }
};

// ETF 검색 (백엔드 API 사용)
export const searchETF = async (query: string): Promise<StockBasicInfo[]> => {
  try {
    const response = await fetch(`/api/etf-search?q=${encodeURIComponent(query)}`);
    if (!response.ok) return [];
    
    const result = await response.json();
    if (result.success && result.data) {
      return result.data.map((item: any) => ({
        code: item.code,
        name: item.name,
        listingDate: '',
        market: item.market || 'ETF',
        sector: 'ETF',
        shareType: 'ETF',
        faceValue: 0,
        listedShares: 0,
      }));
    }
    return [];
  } catch (e) {
    console.error('ETF search failed:', e);
    return [];
  }
};
 
// 상세 종목정보 로드: 우선 백엔드의 병합된 `/api/stock-info/<code>`를 시도하고,
// 실패 시 `public/stock_fundamentals.json`에서 대체 데이터를 사용합니다.
export const getStockDetail = async (code: string): Promise<StockDetailInfo | null> => {
  try {
    // ensure stock list is loaded for name fallback
    await loadStockList();

    // 1) backend merged info
    try {
      const res = await fetch(`/api/stock-info/${encodeURIComponent(code)}`);
      if (res.ok) {
        const j = await res.json();
        if (j.success && j.data) {
          const data = j.data;
          const detail: StockDetailInfo = {
            code,
            name: data.name || stockList.find(s => s.code === code)?.name || 'Unknown',
            currentPrice: data.currentPrice ?? 0,
            per: data.per ?? 0,
            pbr: data.pbr ?? 0,
            eps: data.eps ?? 0,
            marketCap: data.marketCap ?? 0,
            volume: data.volume ?? 0,
            foreignOwnership: data.foreignOwnership ?? 0,
            operatingMargin: data.operatingMargin ?? 0,
            quarterlyMargins: data.quarterlyMargins ?? [],
            foreign_buy: data.foreign_buy ?? 'N/A',
            foreign_sell: data.foreign_sell ?? 'N/A',
            institution_buy: data.institution_buy ?? 'N/A',
            institution_sell: data.institution_sell ?? 'N/A',
            operating_margins: data.operating_margins ?? [],
            major_shareholder_stake: data.major_shareholder_stake ?? 'N/A',
          };
          return detail;
        }
      }
    } catch (err) {
      // ignore and fallback to local fundamentals
      console.debug('Backend /api/stock-info unavailable, falling back', err);
    }

    // 2) local fundamentals JSON fallback
    try {
      const response = await fetch('/stock_fundamentals.json');
      if (response.ok) {
        const fundamentals = await response.json();
        if (fundamentals[code]) {
          const data = fundamentals[code];
          const detail: StockDetailInfo = {
            code,
            name: stockList.find(s => s.code === code)?.name || 'Unknown',
            currentPrice: data.currentPrice ?? 0,
            per: data.per ?? 0,
            pbr: data.pbr ?? 0,
            eps: data.eps ?? 0,
            marketCap: data.marketCap ?? 0,
            volume: data.volume ?? 0,
            foreignOwnership: data.foreignOwnership ?? 0,
            operatingMargin: data.operatingMargin ?? 0,
            quarterlyMargins: data.quarterlyMargins ?? [],
            foreign_buy: data.foreign_buy ?? 'N/A',
            foreign_sell: data.foreign_sell ?? 'N/A',
            institution_buy: data.institution_buy ?? 'N/A',
            institution_sell: data.institution_sell ?? 'N/A',
            operating_margins: data.operating_margins ?? [],
            major_shareholder_stake: data.major_shareholder_stake ?? 'N/A',
          };
          return detail;
        }
      }
    } catch (err) {
      console.debug('Fundamentals file not available', err);
    }
  } catch (e) {
    console.error('getStockDetail failed', e);
  }

  return null;
};

// =============================
// NXT (야간거래) 관련 함수
// =============================

// NXT 종목 캐시
let nxtStocksCache: Set<string> = new Set();
let nxtCacheTime = 0;
let nxtStatusCache: { isNxtHours: boolean; time: number } = { isNxtHours: false, time: 0 };

/**
 * NXT 거래 가능 종목 목록 로드
 */
export const loadNxtStocks = async (): Promise<Set<string>> => {
  const now = Date.now();
  // 1시간 이내면 캐시 사용
  if (nxtStocksCache.size > 0 && (now - nxtCacheTime) < 3600000) {
    return nxtStocksCache;
  }
  
  try {
    const response = await fetch(`${API_BASE_URL}/nxt/stocks`);
    if (response.ok) {
      const data = await response.json();
      if (data.success && data.codes) {
        nxtStocksCache = new Set(data.codes);
        nxtCacheTime = now;
        console.log(`NXT 종목 ${nxtStocksCache.size}개 로드 완료`);
        return nxtStocksCache;
      }
    }
  } catch (e) {
    console.error('NXT 종목 로드 실패:', e);
  }
  return nxtStocksCache;
};

/**
 * 특정 종목이 NXT 거래 가능한지 확인
 */
export const isNxtStock = (code: string): boolean => {
  return nxtStocksCache.has(code.padStart(6, '0'));
};

/**
 * NXT 시간대인지 확인 (17:30~익일 08:00)
 */
export const checkNxtHours = async (): Promise<boolean> => {
  const now = Date.now();
  // 30초 이내면 캐시 사용
  if ((now - nxtStatusCache.time) < 30000) {
    return nxtStatusCache.isNxtHours;
  }
  
  try {
    const response = await fetch(`${API_BASE_URL}/nxt/status`);
    if (response.ok) {
      const data = await response.json();
      if (data.success) {
        nxtStatusCache = { isNxtHours: data.is_nxt_hours, time: now };
        return data.is_nxt_hours;
      }
    }
  } catch (e) {
    // 클라이언트 측 계산 fallback
    const hour = new Date().getHours();
    const minute = new Date().getMinutes();
    const isNxt = (hour > 17 || (hour === 17 && minute >= 30)) || hour < 8;
    nxtStatusCache = { isNxtHours: isNxt, time: now };
    return isNxt;
  }
  return false;
};

/**
 * 여러 종목의 NXT 정보 일괄 조회
 */
export const getNxtInfoBatch = async (codes: string[]): Promise<Record<string, { is_nxt: boolean; is_nxt_hours: boolean }>> => {
  try {
    const response = await fetch(`${API_BASE_URL}/stock-info-batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ codes })
    });
    if (response.ok) {
      const data = await response.json();
      if (data.success) {
        return data.data;
      }
    }
  } catch (e) {
    console.error('NXT 정보 일괄 조회 실패:', e);
  }
  return {};
};

/**
 * NXT 현재가 조회 (NXT 시간대에만 유효)
 */
export const getNxtPrice = async (code: string): Promise<{ currentPrice: number; change: number; changePercent: number } | null> => {
  try {
    const response = await fetch(`${API_BASE_URL}/nxt/price/${code}`);
    if (response.ok) {
      const data = await response.json();
      if (data.success && data.data) {
        return {
          currentPrice: data.data.currentPrice,
          change: data.data.change,
          changePercent: data.data.changePercent
        };
      }
    }
  } catch (e) {
    console.error('NXT 현재가 조회 실패:', e);
  }
  return null;
};

// =============================
// 웹소켓 실시간 가격 API
// =============================

/**
 * 웹소켓 연결 상태 조회
 */
export const getWebSocketStatus = async (): Promise<{
  is_connected: boolean;
  subscribed_count: number;
  subscribed_codes: string[];
  websocket_available: boolean;
}> => {
  try {
    const response = await fetch(`${API_BASE_URL}/ws/status`);
    if (response.ok) {
      const data = await response.json();
      if (data.success) {
        return {
          is_connected: data.is_connected,
          subscribed_count: data.subscribed_count,
          subscribed_codes: data.subscribed_codes || [],
          websocket_available: data.websocket_available
        };
      }
    }
  } catch (e) {
    console.error('웹소켓 상태 조회 실패:', e);
  }
  return { is_connected: false, subscribed_count: 0, subscribed_codes: [], websocket_available: false };
};

/**
 * 웹소켓 연결
 */
export const connectWebSocket = async (): Promise<boolean> => {
  try {
    const response = await fetch(`${API_BASE_URL}/ws/connect`, { method: 'POST' });
    if (response.ok) {
      const data = await response.json();
      return data.success;
    }
  } catch (e) {
    console.error('웹소켓 연결 실패:', e);
  }
  return false;
};

/**
 * 웹소켓 연결 해제
 */
export const disconnectWebSocket = async (): Promise<boolean> => {
  try {
    const response = await fetch(`${API_BASE_URL}/ws/disconnect`, { method: 'POST' });
    if (response.ok) {
      const data = await response.json();
      return data.success;
    }
  } catch (e) {
    console.error('웹소켓 연결 해제 실패:', e);
  }
  return false;
};

/**
 * 종목 웹소켓 구독
 */
export const subscribeWebSocket = async (codes: string[]): Promise<{ success: boolean; subscribed: number }> => {
  try {
    const response = await fetch(`${API_BASE_URL}/ws/subscribe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ codes })
    });
    if (response.ok) {
      const data = await response.json();
      return { success: data.success, subscribed: data.subscribed || 0 };
    }
  } catch (e) {
    console.error('웹소켓 구독 실패:', e);
  }
  return { success: false, subscribed: 0 };
};

/**
 * 종목 웹소켓 구독 해제
 */
export const unsubscribeWebSocket = async (codes: string[]): Promise<boolean> => {
  try {
    const response = await fetch(`${API_BASE_URL}/ws/unsubscribe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ codes })
    });
    if (response.ok) {
      const data = await response.json();
      return data.success;
    }
  } catch (e) {
    console.error('웹소켓 구독 해제 실패:', e);
  }
  return false;
};

/**
 * 등록된 모든 종목 웹소켓 구독
 */
export const subscribeAllRegisteredStocks = async (): Promise<{ success: boolean; subscribed: number; message: string }> => {
  try {
    const response = await fetch(`${API_BASE_URL}/ws/subscribe-all-registered`, { method: 'POST' });
    if (response.ok) {
      const data = await response.json();
      return { 
        success: data.success, 
        subscribed: data.subscribed || 0,
        message: data.message || ''
      };
    }
  } catch (e) {
    console.error('전체 종목 웹소켓 구독 실패:', e);
  }
  return { success: false, subscribed: 0, message: '구독 실패' };
};

/**
 * 웹소켓 실시간 가격 조회
 */
export const getWebSocketPrices = async (): Promise<Record<string, {
  currentPrice: number;
  change: number;
  changePercent: number;
  volume: number;
  timestamp: number;
}>> => {
  try {
    const response = await fetch(`${API_BASE_URL}/ws/prices`);
    if (response.ok) {
      const data = await response.json();
      if (data.success) {
        return data.prices || {};
      }
    }
  } catch (e) {
    console.error('웹소켓 가격 조회 실패:', e);
  }
  return {};
};

// 실제 pykrx 연동을 위해 Python API 서버 필요
// 여기서는 모의 구현
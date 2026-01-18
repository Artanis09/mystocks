import Papa from 'papaparse';
import { ratio } from 'fuzzball';

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
    const response = await fetch(`http://localhost:5000/api/etf-lookup/${code}`);
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
    const response = await fetch(`http://localhost:5000/api/etf-search?q=${encodeURIComponent(query)}`);
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
      const res = await fetch(`http://localhost:5000/api/stock-info/${encodeURIComponent(code)}`);
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
// 실제 pykrx 연동을 위해 Python API 서버 필요
// 여기서는 모의 구현
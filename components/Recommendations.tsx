import React, { useState, useEffect, useCallback, useRef } from 'react';
import { 
  TrendingUp, 
  Sparkles, 
  Target, 
  ArrowUpRight, 
  RefreshCw,
  Search,
  Zap,
  CheckCircle2,
  Calendar,
  AlertCircle,
  BrainCircuit,
  Cpu,
  BarChart2,
  ArrowUpDown,
  Trash2,
  ChevronDown,
  ChevronRight,
  Loader2,
  Clock,
  Database,
  Download,
  TrendingDown,
  LineChart,
  Moon,
  PlusCircle
} from 'lucide-react';
import { RecommendedStock } from '../types';
import { loadNxtStocks, isNxtStock, checkNxtHours } from '../services/stockService';

// Use relative path for API calls to work with domain/proxy
const API_BASE_URL = '/api';

interface RecommendationsProps {
  onStockClick: (stock: RecommendedStock) => void;
}

type SortKey = 'probability' | 'expected_return' | 'name' | 'current_price' | 'model_name';
type SortDirection = 'asc' | 'desc';
type FilterTag = 'filter2';
type ModelName = 'model1' | 'model5' | 'both';  // 'both' 추가

interface SchedulerStatus {
  eod_done_today: boolean;
  intraday_done_today: boolean;
  inference_done_today: boolean;
  crawling_status: 'eod' | 'intraday' | null;
  crawling_start_time: string | null;
  crawling_error: string | null;
}

// 장 운영시간 체크 (08:00 ~ 20:00 사이만 true)
const isMarketHours = (): boolean => {
  const now = new Date();
  const hour = now.getHours();
  return hour >= 8 && hour < 20;
};

// AI Thinking Animation Component
const AIThinkingLoader: React.FC<{ modelName?: string }> = ({ modelName }) => (
  <div className="flex flex-col items-center justify-center py-20 animate-in fade-in duration-700">
    <div className="relative w-24 h-24 mb-8">
      <div className="absolute inset-0 border-4 border-point-cyan/20 rounded-full animate-[spin_3s_linear_infinite]"></div>
      <div className="absolute inset-0 border-4 border-t-point-cyan rounded-full animate-[spin_1.5s_linear_infinite]"></div>
      <div className="absolute inset-4 bg-[#1a1f2e] rounded-full flex items-center justify-center border border-slate-700 shadow-[0_0_30px_rgba(6,182,212,0.3)]">
        <BrainCircuit className="w-8 h-8 text-point-cyan animate-pulse" />
      </div>
    </div>
    <h3 className="text-xl font-black text-white mb-2 tracking-tight">
      {modelName === 'both' ? 'AI 모델1 + 모델2 동시 분석 중' : 'AI Agent가 시장을 분석 중입니다'}
    </h3>
    <p className="text-slate-500 font-medium text-center max-w-md leading-relaxed">
      {modelName === 'both' ? (
        <>
          <span className="text-violet-400 font-bold">모델1(7-class)</span>과{' '}
          <span className="text-emerald-400 font-bold">모델2(LightGBM)</span>를 동시에 실행하여<br/>
          종합적인 추천 종목을 발굴하고 있습니다.
        </>
      ) : (
        <>
          기술적 지표, 수급 데이터, 재무제표를 종합하여<br/>
          <span className="text-point-cyan font-bold">필터2(상승 확률 70% 이상 + 추가 리스크컷)</span>
          를 적용하여 추천 종목을 발굴하고 있습니다.
        </>
      )}
    </p>
  </div>
);

// 데이터 수집 중 메시지 컴포넌트
const CrawlingMessage: React.FC<{ status: SchedulerStatus }> = ({ status }) => (
  <div className="bg-amber-500/10 border border-amber-500/30 rounded-2xl p-8 text-center animate-in fade-in duration-500">
    <div className="w-16 h-16 bg-amber-500/20 rounded-full flex items-center justify-center mx-auto mb-5">
      <Database className="w-8 h-8 text-amber-400 animate-pulse" />
    </div>
    <h3 className="text-lg font-bold text-white mb-2">
      데이터 수집 중입니다
    </h3>
    <p className="text-slate-400 mb-4">
      {status.crawling_status === 'eod' ? '전체 종목 데이터(EOD)를' : '유니버스(시총 500억 이상) 데이터를'} 수집하고 있습니다.<br/>
      잠시만 기다려주세요.
    </p>
    <div className="flex items-center justify-center gap-2 text-sm text-amber-400">
      <Loader2 className="w-4 h-4 animate-spin" />
      <span>수집 시작: {status.crawling_start_time ? new Date(status.crawling_start_time).toLocaleTimeString('ko-KR') : '-'}</span>
    </div>
  </div>
);

// 추천 없음 메시지 컴포넌트
const NoRecommendationsMessage: React.FC<{ hasError: boolean; errorMsg?: string }> = ({ hasError, errorMsg }) => (
  <div className="bg-[#1a1f2e] border border-dashed border-slate-700 rounded-[2rem] py-16 px-10 text-center">
    <div className="w-16 h-16 bg-slate-800 rounded-full flex items-center justify-center mx-auto mb-5">
      {hasError ? (
        <AlertCircle className="w-8 h-8 text-rose-400" />
      ) : (
        <Clock className="w-8 h-8 text-slate-500 opacity-50" />
      )}
    </div>
    <h3 className="text-lg font-bold text-white mb-2">
      {hasError ? 'AI 분석 중 오류가 발생했습니다' : '오늘의 추천 종목이 아직 없습니다'}
    </h3>
    <p className="text-slate-500">
      {hasError ? errorMsg : '상단의 "AI 예측" 버튼을 눌러 분석을 시작하거나, 오후 3시 이후 자동 분석을 기다려주세요.'}
    </p>
  </div>
);


export const Recommendations: React.FC<RecommendationsProps> = ({ onStockClick }) => {
  const [recommendationsByFilter, setRecommendationsByFilter] = useState<Record<FilterTag, RecommendedStock[]>>({
    filter2: []
  });
  const [isLoading, setIsLoading] = useState(true);
  const [predictingFilter, setPredictingFilter] = useState<FilterTag | null>(null);
  const [modelName, setModelName] = useState<ModelName>('both');  // 기본값: both (동시 실행)
  const [errorByFilter, setErrorByFilter] = useState<Record<FilterTag, string | null>>({
    filter2: null
  });
  
  // 스케줄러 상태
  const [schedulerStatus, setSchedulerStatus] = useState<SchedulerStatus | null>(null);
  
  // 일자별 접기/펼치기 상태 (기본: 오늘만 펼침)
  const [expandedDates, setExpandedDates] = useState<Set<string>>(new Set());
  
  // 실시간 가격 상태
  const [realtimePrices, setRealtimePrices] = useState<Record<string, { current_price: number; change_percent: number }>>({});
  
  // KIS API 상태 (실시간 가격 조회 가능 여부)
  const [kisApiStatus, setKisApiStatus] = useState<{ available: boolean; error: string | null }>({
    available: true,
    error: null
  });
  
  // NXT 상태
  const [isNxtHours, setIsNxtHours] = useState(false);
  
  // 정렬 상태
  const [sortConfig, setSortConfig] = useState<{ key: SortKey; direction: SortDirection }>({
    key: 'expected_return',
    direction: 'desc'
  });
  
  // 체크박스 다중 선택 상태
  const [selectedStocks, setSelectedStocks] = useState<Set<string>>(new Set()); // date_code 형식
  
  // 자동매매 등록 여부 상태
  const [registeredCodes, setRegisteredCodes] = useState<Set<string>>(new Set());

  // Refs for visibility tracking
  const stockRowRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const observerRef = useRef<IntersectionObserver | null>(null);
  const visibleCodesRef = useRef<Set<string>>(new Set());
  const isFetchingPricesRef = useRef(false);

  // 오늘 날짜
  const today = new Date().toLocaleDateString('en-CA');

  // NXT 상태
  const [nxtLoaded, setNxtLoaded] = useState(false);
  
  // NXT 상태 로드 및 체크
  useEffect(() => {
    const loadNxtData = async () => {
      try {
        await loadNxtStocks();
        setNxtLoaded(true);
        const nxtHours = await checkNxtHours();
        setIsNxtHours(nxtHours);
      } catch (e) {
        console.error('NXT 데이터 로드 실패:', e);
      }
    };
    loadNxtData();
    
    // 5분마다 NXT 상태 갱신
    const interval = setInterval(async () => {
      const nxtHours = await checkNxtHours();
      setIsNxtHours(nxtHours);
    }, 300000);
    return () => clearInterval(interval);
  }, []);

  // 스케줄러 상태 조회
  const fetchSchedulerStatus = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/scheduler/status`);
      if (response.ok) {
        const data = await response.json();
        setSchedulerStatus(data);
      }
    } catch (err) {
      console.error('Failed to fetch scheduler status:', err);
    }
  };

  const fetchRecommendations = async (filterTag: FilterTag, refresh = false) => {
    if (refresh) {
      setPredictingFilter(filterTag);
      setErrorByFilter(prev => ({ ...prev, [filterTag]: null }));
      try {
        // 'both' 모드일 경우 두 모델 동시 실행
        if (modelName === 'both') {
          // 두 모델 병렬 실행
          const [res1, res2] = await Promise.allSettled([
            fetch(`${API_BASE_URL}/recommendations/predict?filter=${filterTag}&model=model1`, { method: 'POST' }),
            fetch(`${API_BASE_URL}/recommendations/predict?filter=${filterTag}&model=model5`, { method: 'POST' })
          ]);
          
          // 에러 체크
          const errors: string[] = [];
          if (res1.status === 'rejected' || (res1.status === 'fulfilled' && !res1.value.ok)) {
            errors.push('모델1 예측 실패');
          }
          if (res2.status === 'rejected' || (res2.status === 'fulfilled' && !res2.value.ok)) {
            errors.push('모델2 예측 실패');
          }
          
          if (errors.length === 2) {
            throw new Error('모델1, 모델2 모두 예측에 실패했습니다.');
          } else if (errors.length === 1) {
            console.warn(errors[0]);
            // 하나라도 성공하면 계속 진행
          }
        } else {
          // 단일 모델 실행
          const response = await fetch(`${API_BASE_URL}/recommendations/predict?filter=${filterTag}&model=${modelName}`, {
            method: 'POST'
          });
          if (!response.ok) {
            let errData: any = null;
            try {
              errData = await response.json();
            } catch {
              // ignore
            }
            const baseMsg = errData?.error || 'Prediction failed';
            const backendPython = errData?.backend_python ? `\n\nbackend_python: ${errData.backend_python}` : '';
            const howToFix = Array.isArray(errData?.how_to_fix) ? `\n\nHow to fix:\n- ${errData.how_to_fix.join('\n- ')}` : '';
            throw new Error(`${baseMsg}${backendPython}${howToFix}`);
          }
        }
        await fetchRecommendations(filterTag, false);
      } catch (err: any) {
        setErrorByFilter(prev => ({ ...prev, [filterTag]: err.message || 'AI 분석 중 오류가 발생했습니다' }));
        console.error(err);
      } finally {
        setPredictingFilter(null);
      }
      return;
    }

    // GET 조회 - 'both' 모드일 경우 두 모델 결과 병합
    try {
      if (modelName === 'both') {
        const [res1, res2] = await Promise.all([
          fetch(`${API_BASE_URL}/recommendations?filter=${filterTag}&model=model1`),
          fetch(`${API_BASE_URL}/recommendations?filter=${filterTag}&model=model5`)
        ]);
        
        // KIS API 상태 헤더 읽기 (첫 번째 응답에서)
        const kisAvailable = res1.headers.get('X-KIS-Available') !== 'false';
        const kisError = res1.headers.get('X-KIS-Error');
        setKisApiStatus({ available: kisAvailable, error: kisError });
        
        let combined: RecommendedStock[] = [];
        
        if (res1.ok) {
          const data1 = await res1.json();
          combined = [...combined, ...data1.map((item: any) => ({
            ...item,
            close: item.base_price || item.close,
            model_name: 'model1',
          }))];
        }
        
        if (res2.ok) {
          const data2 = await res2.json();
          combined = [...combined, ...data2.map((item: any) => ({
            ...item,
            close: item.base_price || item.close,
            model_name: 'model5',
          }))];
        }
        
        // 중복 종목 병합 (같은 날짜, 같은 종목코드는 M1+M2로 표시)
        const uniqueMap = new Map<string, RecommendedStock>();
        combined.forEach(stock => {
          const key = `${stock.date}_${stock.code}`;  // 날짜+종목코드로만 키 생성
          if (uniqueMap.has(key)) {
            // 이미 있는 종목이면 모델명 병합
            const existing = uniqueMap.get(key)!;
            const existingModels = existing.model_name || '';
            const newModel = stock.model_name || '';
            // 이미 병합된 경우 중복 추가 방지
            if (!existingModels.includes(newModel)) {
              existing.model_name = existingModels.includes('model1') && newModel === 'model5' 
                ? 'model1+model5' 
                : newModel.includes('model1') && existingModels === 'model5'
                ? 'model1+model5'
                : existingModels + '+' + newModel;
            }
            // 확률과 기대수익률은 더 높은 값으로
            if (stock.probability > (existing.probability || 0)) {
              existing.probability = stock.probability;
            }
            if (stock.expected_return > (existing.expected_return || 0)) {
              existing.expected_return = stock.expected_return;
            }
          } else {
            uniqueMap.set(key, { ...stock });
          }
        });
        
        const processed = Array.from(uniqueMap.values());
        setRecommendationsByFilter(prev => ({ ...prev, [filterTag]: processed }));
        
        // 오늘 날짜는 기본 펼침
        setExpandedDates(prev => {
          const newSet = new Set(prev);
          newSet.add(today);
          return newSet;
        });
      } else {
        const response = await fetch(`${API_BASE_URL}/recommendations?filter=${filterTag}&model=${modelName}`);
        if (response.ok) {
          // KIS API 상태 헤더 읽기
          const kisAvailable = response.headers.get('X-KIS-Available') !== 'false';
          const kisError = response.headers.get('X-KIS-Error');
          setKisApiStatus({ available: kisAvailable, error: kisError });
          
          const data = await response.json();
          const processed = data.map((item: any) => ({
            ...item,
            close: item.base_price || item.close,
            model_name: modelName,
          }));
          setRecommendationsByFilter(prev => ({ ...prev, [filterTag]: processed }));
          
          // 오늘 날짜는 기본 펼침
          setExpandedDates(prev => {
            const newSet = new Set(prev);
            newSet.add(today);
            return newSet;
          });
        } else {
          const errData = await response.json();
          setErrorByFilter(prev => ({ ...prev, [filterTag]: errData.error || 'Failed to fetch recommendations' }));
        }
      }
    } catch (err) {
      setErrorByFilter(prev => ({ ...prev, [filterTag]: 'Connection to backend failed' }));
      console.error(err);
    }
  };

  // 실시간 가격 조회 (보이는 종목만, 장 운영시간에만)
  const fetchRealtimePrices = useCallback(async () => {
    // 장외 시간 (20:00 ~ 08:00)에는 실시간 조회 안함
    if (!isMarketHours()) {
      return;
    }
    
    // 이미 요청 중이면 스킵
    if (isFetchingPricesRef.current) return;
    
    const codes = Array.from(visibleCodesRef.current).slice(0, 20);
    if (codes.length === 0) return;
    
    isFetchingPricesRef.current = true;
    try {
      const response = await fetch(`${API_BASE_URL}/realtime-prices`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ codes })
      });
      if (response.ok) {
        const data = await response.json();
        setRealtimePrices(prev => ({ ...prev, ...data }));
      }
    } catch (err) {
      console.error('Failed to fetch realtime prices:', err);
    } finally {
      isFetchingPricesRef.current = false;
    }
  }, []);

  // 초기 로드 - 데이터가 없을 때만 호출
  useEffect(() => {
    // 이미 데이터가 있으면 스킵 (페이지 이동 후 복귀 시)
    const existingData = recommendationsByFilter['filter2'];
    if (existingData && existingData.length > 0) {
      // 스케줄러 상태만 업데이트
      fetchSchedulerStatus();
      return;
    }
    
    setIsLoading(true);
    Promise.all([
      fetchRecommendations('filter2', false),
      fetchSchedulerStatus()
    ]).finally(() => setIsLoading(false));
  }, [modelName]);

  // 스케줄러 상태 주기적 조회
  useEffect(() => {
    const interval = setInterval(() => {
      fetchSchedulerStatus();
    }, schedulerStatus?.crawling_status ? 5000 : 30000);
    return () => clearInterval(interval);
  }, [schedulerStatus?.crawling_status]);

  // 실시간 가격 5초마다 폴링 (한 번만 설정)
  useEffect(() => {
    // 초기 로드 후 1초 뒤에 첫 조회 (데이터 로드 대기)
    const initialTimeout = setTimeout(fetchRealtimePrices, 1000);
    const interval = setInterval(fetchRealtimePrices, 5000);
    return () => {
      clearTimeout(initialTimeout);
      clearInterval(interval);
    };
  }, []);

  // IntersectionObserver 설정
  useEffect(() => {
    observerRef.current = new IntersectionObserver(
      (entries) => {
        entries.forEach(entry => {
          const code = entry.target.getAttribute('data-code');
          if (code) {
            // ref를 직접 수정 (상태 변경 없음 = 리렌더링 없음)
            if (entry.isIntersecting) {
              visibleCodesRef.current.add(code);
            } else {
              visibleCodesRef.current.delete(code);
            }
          }
        });
      },
      { threshold: 0.1 }
    );
    return () => {
      observerRef.current?.disconnect();
    };
  }, []);

  // 종목 행 ref 등록
  const setStockRowRef = useCallback((code: string, el: HTMLDivElement | null) => {
    if (el) {
      stockRowRefs.current.set(code, el);
      observerRef.current?.observe(el);
    } else {
      const existing = stockRowRefs.current.get(code);
      if (existing) {
        observerRef.current?.unobserve(existing);
        stockRowRefs.current.delete(code);
      }
    }
  }, []);

  // 정렬 핸들러
  const handleSort = (key: SortKey) => {
    setSortConfig(prev => ({
      key,
      direction: prev.key === key && prev.direction === 'desc' ? 'asc' : 'desc'
    }));
  };

  // 일자 접기/펼치기 토글
  const toggleDateExpansion = (date: string) => {
    setExpandedDates(prev => {
      const newSet = new Set(prev);
      if (newSet.has(date)) {
        newSet.delete(date);
      } else {
        newSet.add(date);
      }
      return newSet;
    });
  };

  // 유틸리티 함수들 (핸들러에서 사용하므로 먼저 정의)
  const formatPrice = (price?: number) => {
    if (price === undefined || price === null) return '-';
    return new Intl.NumberFormat('ko-KR').format(price);
  };

  const formatMarketCap = (cap: number) => {
    const eok = Math.round(cap / 100000000);
    if (eok >= 10000) {
      return (eok / 10000).toFixed(1) + '조';
    }
    return eok + '억';
  };

  const formatPercent = (val: number) => {
    return (val * 100).toFixed(1) + '%';
  };

  const formatReturnRate = (val?: number) => {
    if (val === undefined) return '-';
    return val.toFixed(2) + '%';
  };

  // 자동매매 유니버스에 추가
  const handleAddToUniverse = async (stocksToRegister: RecommendedStock | RecommendedStock[]) => {
    const isArray = Array.isArray(stocksToRegister);
    const stocksArr = isArray ? stocksToRegister : [stocksToRegister];
    
    if (stocksArr.length === 0) return;

    const confirmMsg = isArray 
      ? `선택한 ${stocksArr.length}개 종목을 자동매매 대상(유니버스)으로 등록하시겠습니까?`
      : `${stocksArr[0].name} 종목을 자동매매 대상(유니버스)으로 등록하시겠습니까?`;

    if (!window.confirm(confirmMsg)) return;

    try {
      const payload = {
        stocks: stocksArr.map(s => ({
          code: s.code,
          name: s.name,
          basePrice: s.base_price || s.close || 0,
          marketCap: s.market_cap,
          source: (s.model_name || 'recom') as any,
          probability: s.probability,
          modelName: s.model_name,
          addedDate: s.date
        }))
      };

      const response = await fetch(`${API_BASE_URL}/auto-trading/target-stocks`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });

      if (response.ok) {
        const result = await response.json();
        alert(`${result.added}개 종목이 자동매매 유니버스에 등록되었습니다.`);
        // 등록 후 등록 상태 갱신
        await fetchRegisteredCodes();
        // 선택 초기화
        setSelectedStocks(new Set());
      } else {
        const errorData = await response.json();
        alert(`등록 실패: ${errorData.error || '알 수 없는 오류'}`);
      }
    } catch (err) {
      console.error('Error adding to universe:', err);
      alert('등록 중 오류가 발생했습니다.');
    }
  };

  // 자동매매 등록 여부 확인 (현재 표시되는 종목들의 등록 상태 확인)
  const fetchRegisteredCodes = useCallback(async () => {
    const allRecommendations = recommendationsByFilter.filter2;
    if (allRecommendations.length === 0) return;
    
    const codes = [...new Set(allRecommendations.map(s => s.code))];
    try {
      const response = await fetch(`${API_BASE_URL}/auto-trading/target-stocks/check`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ codes })
      });
      if (response.ok) {
        const data = await response.json();
        setRegisteredCodes(new Set(data.registered || []));
      }
    } catch (err) {
      console.error('Error checking registered codes:', err);
    }
  }, [recommendationsByFilter.filter2]);
  
  // 추천 목록이 바뀔 때마다 등록 상태 확인
  useEffect(() => {
    if (recommendationsByFilter.filter2.length > 0) {
      fetchRegisteredCodes();
    }
  }, [recommendationsByFilter.filter2, fetchRegisteredCodes]);

  // 체크박스 전체 선택/해제 (특정 날짜)
  const handleSelectAllForDate = (date: string, stocks: RecommendedStock[]) => {
    setSelectedStocks(prev => {
      const newSet = new Set(prev);
      const stockKeys = stocks.map(s => `${s.date}_${s.code}`);
      
      // 해당 날짜의 모든 종목이 이미 선택되어 있는지 확인
      const allSelected = stockKeys.every(key => prev.has(key));
      
      if (allSelected) {
        // 전체 해제
        stockKeys.forEach(key => newSet.delete(key));
      } else {
        // 전체 선택
        stockKeys.forEach(key => newSet.add(key));
      }
      return newSet;
    });
  };

  // 체크박스 개별 선택/해제
  const handleSelectStock = (date: string, code: string) => {
    const key = `${date}_${code}`;
    setSelectedStocks(prev => {
      const newSet = new Set(prev);
      if (prev.has(key)) {
        newSet.delete(key);
      } else {
        newSet.add(key);
      }
      return newSet;
    });
  };

  // 선택된 종목들 일괄 등록
  const handleBulkRegister = async (date: string, stocks: RecommendedStock[]) => {
    const selectedForDate = stocks.filter(s => selectedStocks.has(`${s.date}_${s.code}`));
    if (selectedForDate.length === 0) {
      alert('등록할 종목을 선택해주세요.');
      return;
    }
    await handleAddToUniverse(selectedForDate);
  };

  const handleDeleteList = async (e: React.MouseEvent, date: string, filterTag: FilterTag) => {
    e.stopPropagation();
    if (!window.confirm(`${date} 날짜의 추천 목록을 삭제하시겠습니까?`)) {
      return;
    }
    try {
      const response = await fetch(`${API_BASE_URL}/recommendations?date=${date}&filter=${filterTag}&model=${modelName}`, {
        method: 'DELETE'
      });
      if (response.ok) {
        setRecommendationsByFilter(prev => ({
          ...prev,
          [filterTag]: prev[filterTag].filter(s => s.date !== date)
        }));
      } else {
        const data = await response.json();
        alert(`삭제 실패: ${data.error}`);
      }
    } catch (err) {
      console.error(err);
      alert('삭제 중 오류가 발생했습니다.');
    }
  };

  // 개별 종목 삭제
  const handleDeleteStock = async (e: React.MouseEvent, stock: RecommendedStock) => {
    e.stopPropagation();
    if (!window.confirm(`${stock.name} (${stock.code})을(를) 삭제하시겠습니까?`)) {
      return;
    }
    try {
      const response = await fetch(`${API_BASE_URL}/recommendations/${stock.id}`, {
        method: 'DELETE'
      });
      if (response.ok) {
        setRecommendationsByFilter(prev => ({
          ...prev,
          filter2: prev.filter2.filter(s => s.id !== stock.id)
        }));
      } else {
        const data = await response.json();
        alert(`삭제 실패: ${data.error}`);
      }
    } catch (err) {
      console.error(err);
      alert('삭제 중 오류가 발생했습니다.');
    }
  };

  // 크롤링 중 확인
  const isCrawling = schedulerStatus?.crawling_status != null;

  if (predictingFilter) {
    return (
      <div className="p-8 max-w-7xl mx-auto">
        <AIThinkingLoader modelName={modelName} />
      </div>
    );
  }

  const renderSection = (filterTag: FilterTag, title: string, subtitle: string) => {
    const recommendations = recommendationsByFilter[filterTag] || [];
    const error = errorByFilter[filterTag];

    // 날짜별로 그룹핑
    const grouped = recommendations.reduce((acc, stock) => {
      const date = stock.date || 'Unknown';
      if (!acc[date]) acc[date] = [];
      acc[date].push(stock);
      return acc;
    }, {} as Record<string, RecommendedStock[]>);

    // 날짜 내림차순 정렬
    const sortedDates = Object.keys(grouped).sort((a, b) => new Date(b).getTime() - new Date(a).getTime());

    // 오늘 추천 존재 여부
    const hasTodayRecommendations = (grouped[today]?.length || 0) > 0;

    return (
      <div className="space-y-6">
        <div className="flex items-start justify-between gap-6">
          <div>
            <h2 className="text-xl font-black text-white flex items-center gap-2">
              {title}
            </h2>
            <p className="text-slate-500 mt-1 font-medium">{subtitle}</p>
          </div>
        </div>

        {error && (
          <div className="bg-rose-500/10 border border-rose-500/30 rounded-2xl p-4 text-center animate-in slide-in-from-top-2">
            <p className="text-rose-400 font-bold flex items-center justify-center gap-2">
              <AlertCircle className="w-5 h-5" />
              {error}
            </p>
          </div>
        )}

        {isLoading ? (
          <div className="space-y-4">
            {[1, 2].map(i => (
              <div key={i} className="h-24 bg-[#1a1f2e] rounded-2xl animate-pulse" />
            ))}
          </div>
        ) : isCrawling && schedulerStatus ? (
          <CrawlingMessage status={schedulerStatus} />
        ) : recommendations.length === 0 ? (
          <NoRecommendationsMessage hasError={!!error} errorMsg={error || undefined} />
        ) : (
          <div className="space-y-4 animate-in fade-in duration-500">
            {/* 오늘 추천이 없으면 안내 메시지 */}
            {!hasTodayRecommendations && (
              <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-4 mb-4">
                <p className="text-slate-400 text-sm flex items-center gap-2">
                  <Clock className="w-4 h-4" />
                  오늘({today})의 추천 종목이 아직 없습니다. "AI 예측" 버튼을 눌러 분석을 시작하세요.
                </p>
              </div>
            )}

            {sortedDates.map(date => {
              const isToday = date === today;
              const isExpanded = expandedDates.has(date);
              let stocks = [...grouped[date]];

              // 정렬 적용
              stocks.sort((a, b) => {
                let valA: any = a[sortConfig.key];
                let valB: any = b[sortConfig.key];

                if (sortConfig.key === 'current_price') {
                  const priceA = realtimePrices[a.code]?.current_price ?? a.current_price ?? 0;
                  const priceB = realtimePrices[b.code]?.current_price ?? b.current_price ?? 0;
                  valA = priceA;
                  valB = priceB;
                }

                if (valA < valB) return sortConfig.direction === 'asc' ? -1 : 1;
                if (valA > valB) return sortConfig.direction === 'asc' ? 1 : -1;
                return 0;
              });

              return (
                <div key={`${filterTag}_${date}`} className="relative">
                  {/* Date Header - Clickable */}
                  <div
                    className="flex items-center gap-4 mb-2 cursor-pointer hover:bg-slate-800/30 rounded-xl p-2 -ml-2 transition-colors"
                    onClick={() => toggleDateExpansion(date)}
                  >
                    <div className="text-slate-400">
                      {isExpanded ? <ChevronDown className="w-5 h-5" /> : <ChevronRight className="w-5 h-5" />}
                    </div>
                    <div className={`px-4 py-1.5 rounded-lg text-sm font-black flex items-center gap-2 ${
                      isToday ? 'bg-point-cyan text-white shadow-lg shadow-point-cyan/20' : 'bg-slate-800 text-slate-400'
                    }`}>
                      <Calendar className="w-4 h-4" />
                      {date}
                    </div>
                    <div className="text-sm text-slate-500">{stocks.length}종목</div>
                    <div className="h-px bg-slate-800 flex-1"></div>

                    {/* Add to Universe Button */}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleBulkRegister(date, stocks);
                      }}
                      className="p-2 hover:bg-emerald-500/10 text-slate-500 hover:text-emerald-400 rounded-lg transition-all flex items-center gap-1 text-xs font-bold"
                      title={`선택한 종목 자동매매 등록`}
                    >
                      <PlusCircle className="w-4 h-4" />
                      선택 등록 ({stocks.filter(s => selectedStocks.has(`${s.date}_${s.code}`)).length})
                    </button>

                    {/* Delete Date Group Button */}
                    <button
                      onClick={(e) => handleDeleteList(e, date, filterTag)}
                      className="p-2 hover:bg-rose-500/10 text-slate-500 hover:text-rose-400 rounded-lg transition-all"
                      title={`${date} 목록 삭제`}
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>

                  {/* Collapsible Content */}
                  {isExpanded && (
                    <div className="bg-[#1a1f2e] border border-slate-800 rounded-2xl overflow-hidden shadow-xl animate-in slide-in-from-top-2 duration-200">
                      {/* Table Header */}
                      <div className="grid grid-cols-12 gap-2 p-4 bg-[#151925] border-b border-slate-800 text-xs font-bold text-slate-500 uppercase tracking-wider select-none">
                        {/* 체크박스 열 */}
                        <div className="col-span-1 flex items-center justify-center">
                          <input
                            type="checkbox"
                            checked={stocks.length > 0 && stocks.every(s => selectedStocks.has(`${s.date}_${s.code}`))}
                            onChange={() => handleSelectAllForDate(date, stocks)}
                            className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-point-cyan focus:ring-point-cyan focus:ring-offset-0 cursor-pointer"
                            title="전체 선택/해제"
                          />
                        </div>
                        <div
                          className="col-span-3 pl-2 cursor-pointer hover:text-white flex items-center gap-1"
                          onClick={() => handleSort('name')}
                        >
                          종목명 {sortConfig.key === 'name' && <ArrowUpDown className="w-3 h-3" />}
                        </div>
                        <div className="col-span-1 text-right">추천가</div>
                        <div
                          className="col-span-2 text-right cursor-pointer hover:text-white flex items-center justify-end gap-1"
                          onClick={() => handleSort('current_price')}
                        >
                          현재가 {sortConfig.key === 'current_price' && <ArrowUpDown className="w-3 h-3" />}
                        </div>
                        <div
                          className="col-span-2 text-right cursor-pointer hover:text-white flex items-center justify-end gap-1"
                          onClick={() => handleSort('probability')}
                        >
                          확률 {sortConfig.key === 'probability' && <ArrowUpDown className="w-3 h-3" />}
                        </div>
                        <div
                          className="col-span-2 text-right cursor-pointer hover:text-white flex items-center justify-end gap-1"
                          onClick={() => handleSort('expected_return')}
                        >
                          기대수익 {sortConfig.key === 'expected_return' && <ArrowUpDown className="w-3 h-3" />}
                        </div>
                        <div className="col-span-1 text-center">액션</div>
                      </div>

                      {/* Table Body */}
                      {stocks.map((stock, idx) => {
                        // 실시간 가격 (있으면 사용, 없으면 기존 값)
                        const rtPrice = realtimePrices[stock.code];
                        const currentPrice = rtPrice?.current_price ?? stock.current_price ?? stock.base_price;
                        const currentChange = rtPrice?.change_percent ?? stock.current_change ?? 0;
                        // 가격 출처: 'realtime' | 'local' | 'base'
                        const priceSource = rtPrice ? 'realtime' : (stock as any).price_source || 'base';

                        const returnRate = stock.base_price > 0
                          ? (currentPrice - stock.base_price) / stock.base_price * 100
                          : 0;
                        const isPositive = returnRate >= 0;
                        
                        // NXT 거래 가능 여부 확인 (nxtLoaded가 true일 때만 isNxtStock 검사)
                        const stockIsNxt = stock.is_nxt ?? (nxtLoaded ? isNxtStock(stock.code) : false);
                        
                        // 자동매매 등록 여부
                        const isRegistered = registeredCodes.has(stock.code);
                        
                        return (
                          <div
                            key={`${filterTag}_${stock.id || stock.code}_${idx}`}
                            ref={(el) => setStockRowRef(stock.code, el)}
                            data-code={stock.code}
                            onClick={() => onStockClick(stock)}
                            className={`grid grid-cols-12 gap-2 p-4 border-b border-slate-800/50 hover:bg-slate-800/50 cursor-pointer transition-colors group items-center ${
                              isRegistered ? 'bg-emerald-500/5' : ''
                            }`}
                          >
                            {/* 체크박스 */}
                            <div className="col-span-1 flex items-center justify-center">
                              <input
                                type="checkbox"
                                checked={selectedStocks.has(`${stock.date}_${stock.code}`)}
                                onChange={(e) => {
                                  e.stopPropagation();
                                  handleSelectStock(stock.date, stock.code);
                                }}
                                onClick={(e) => e.stopPropagation()}
                                className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-point-cyan focus:ring-point-cyan focus:ring-offset-0 cursor-pointer"
                              />
                            </div>

                            {/* Name & Code with Model Badge + 등록 배지 */}
                            <div className="col-span-3 flex flex-col justify-center pl-2">
                              <div className="flex items-center gap-2">
                                <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold flex-shrink-0 ${
                                  stock.model_name?.includes('model1') && stock.model_name?.includes('model5')
                                    ? 'bg-gradient-to-r from-violet-500/20 to-emerald-500/20 text-yellow-400'  // M1+M2
                                    : stock.model_name === 'model1' 
                                    ? 'bg-violet-500/20 text-violet-400' 
                                    : 'bg-emerald-500/20 text-emerald-400'
                                }`}>
                                  {stock.model_name?.includes('model1') && stock.model_name?.includes('model5') 
                                    ? 'M1+M2' 
                                    : stock.model_name === 'model1' ? 'M1' : 'M2'}
                                </span>
                                <span className="text-white font-bold group-hover:text-point-cyan transition-colors truncate">{stock.name}</span>
                                {isRegistered && (
                                  <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-emerald-500/20 text-emerald-400 flex-shrink-0 flex items-center gap-0.5">
                                    <CheckCircle2 className="w-2.5 h-2.5" />등록
                                  </span>
                                )}
                                {stock.probability >= 0.9 && (
                                  <Zap className="w-3 h-3 text-yellow-400 fill-yellow-400 flex-shrink-0" />
                                )}
                                {stockIsNxt && (
                                  <span className="flex items-center gap-0.5 px-1 py-0.5 bg-indigo-500/20 text-indigo-400 text-[8px] font-bold rounded flex-shrink-0" title="NXT(야간거래) 가능">
                                    <Moon className="w-2 h-2" />NXT
                                  </span>
                                )}
                              </div>
                              <span className="text-xs text-slate-500 font-mono">{stock.code} · {formatMarketCap(stock.market_cap)}</span>
                            </div>

                            {/* Base Price */}
                            <div className="col-span-1 text-right text-slate-400 font-mono text-sm">
                              {formatPrice(stock.base_price)}원
                            </div>

                            {/* Current Price & Return Rate */}
                            <div className="col-span-2 text-right">
                              <div className="font-mono text-sm font-bold text-white mb-0.5 flex items-center justify-end gap-1">
                                {formatPrice(currentPrice)}원
                                {priceSource === 'realtime' && (
                                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" title="실시간" />
                                )}
                                {priceSource === 'local' && (
                                  <span className="w-2 h-2 rounded-full bg-amber-400" title="장중" />
                                )}
                                {priceSource === 'base' && (
                                  <span className="w-2 h-2 rounded-full bg-slate-500" title="기준가" />
                                )}
                              </div>
                              <div className="flex flex-col items-end">
                                <div className={`text-[10px] font-bold ${
                                  currentChange >= 0 ? 'text-emerald-400' : 'text-rose-400'
                                }`}>
                                  당일 {currentChange >= 0 ? '+' : ''}{currentChange.toFixed(2)}%
                                </div>
                                <div className={`text-xs font-bold px-1.5 py-0.5 rounded-md mt-0.5 ${
                                  isPositive ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'
                                }`}>
                                  추천대비 {isPositive ? '+' : ''}{returnRate.toFixed(2)}%
                                </div>
                              </div>
                            </div>

                            {/* Probability */}
                            <div className="col-span-2 text-right pr-4">
                              <span className="text-sm font-bold text-point-cyan">{formatPercent(stock.probability)}</span>
                            </div>

                            {/* Expected Return */}
                            <div className="col-span-2 text-right pr-4">
                              <span className="text-sm font-bold text-emerald-400">+{formatPercent(stock.expected_return)}</span>
                            </div>

                            {/* Action Buttons */}
                            <div className="col-span-1 flex items-center justify-center gap-1">
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleAddToUniverse(stock);
                                }}
                                className="p-1.5 hover:bg-emerald-500/10 text-slate-500 hover:text-emerald-400 rounded-lg transition-all"
                                title="자동매매 등록"
                              >
                                <PlusCircle className="w-3.5 h-3.5" />
                              </button>
                              <button
                                onClick={(e) => handleDeleteStock(e, stock)}
                                className="p-1.5 hover:bg-slate-700 text-slate-500 hover:text-slate-300 rounded-lg transition-all"
                                title="삭제"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  };

  // 장외 시간 여부
  const isAfterHours = !isMarketHours();

  return (
    <div className="p-4 md:p-8 max-w-7xl mx-auto">
      {/* Header - 모바일 반응형 */}
      <div className="flex flex-col md:flex-row md:items-center justify-between mb-6 md:mb-8 gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-black text-white flex items-center gap-2 md:gap-3">
            <Sparkles className="w-6 h-6 md:w-8 md:h-8 text-point-cyan" />
            AI 추천
          </h1>
          <p className="text-slate-500 mt-1 md:mt-2 text-sm md:text-base font-medium">
            {modelName === 'both' 
              ? '모델1 + 모델2를 동시에 실행하여 통합 추천 종목을 표시합니다.' 
              : '모델 선택 후 "AI 예측"을 누르면 필터2로 예측을 실행합니다.'}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 md:gap-3">
          {/* NXT 시간 표시 */}
          {isNxtHours && (
            <div className="flex items-center gap-1.5 text-xs text-indigo-400 bg-indigo-500/20 px-2 py-1 rounded-lg font-bold" title="야간거래 시간 (17:30~08:00)">
              <Moon className="w-3 h-3" />
              NXT
            </div>
          )}
          
          {/* 장외 시간 표시 */}
          {isAfterHours && !isNxtHours && (
            <div className="flex items-center gap-1.5 text-xs text-slate-500 bg-slate-800/50 px-2 py-1 rounded-lg">
              <Moon className="w-3 h-3" />
              장외 시간
            </div>
          )}
          
          {/* 스케줄러 상태 표시 */}
          {schedulerStatus && (
            <div className="flex items-center gap-2 text-xs text-slate-500">
              {schedulerStatus.crawling_status && (
                <span className="flex items-center gap-1 text-amber-400">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  {schedulerStatus.crawling_status === 'eod' ? 'EOD 수집중' : '장중 수집중'}
                </span>
              )}
              {schedulerStatus.inference_done_today && (
                <span className="flex items-center gap-1 text-emerald-400">
                  <CheckCircle2 className="w-3 h-3" />
                  오늘 분석 완료
                </span>
              )}
            </div>
          )}

          <label className="text-sm text-slate-400 font-semibold hidden md:block">모델 선택</label>
          <select
            value={modelName}
            onChange={(e) => setModelName(e.target.value as ModelName)}
            className="bg-[#1a1f2e] border border-slate-700 text-white text-sm px-3 py-2 rounded-xl focus:outline-none focus:border-point-cyan flex-shrink-0"
          >
            <option value="both">🔥 모델1+2 동시</option>
            <option value="model1">모델1 (7-class)</option>
            <option value="model5">모델2 (LightGBM)</option>
          </select>

          <button
            onClick={() => fetchRecommendations('filter2', true)}
            disabled={isCrawling}
            className="flex items-center gap-2 px-3 md:px-4 py-2 rounded-xl bg-point-cyan text-white font-bold hover:bg-point-cyan/90 transition-all disabled:opacity-50 disabled:cursor-not-allowed text-sm md:text-base"
          >
            <Zap className="w-4 h-4" />
            AI 예측
          </button>
        </div>
      </div>

      {/* KIS API 연결 상태 경고 (사용 불가 시에만 표시) */}
      {!kisApiStatus.available && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-2xl p-3 md:p-4 mb-4 md:mb-6 animate-in fade-in duration-300">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 md:w-10 md:h-10 rounded-xl bg-amber-500/20 flex items-center justify-center flex-shrink-0">
              <AlertCircle className="w-4 h-4 md:w-5 md:h-5 text-amber-400" />
            </div>
            <div className="flex-1 min-w-0">
              <h4 className="text-amber-400 font-bold text-xs md:text-sm">실시간 시세 조회 불가</h4>
              <p className="text-slate-400 text-[10px] md:text-xs mt-0.5 truncate">
                KIS API 연결에 문제가 있어 기준가를 표시합니다.
              </p>
            </div>
          </div>
        </div>
      )}

      <div className="space-y-12">
        {renderSection(
          'filter2',
          '오늘의 AI Pick!',
          'Prob≥70% + 시총≥500억 + Daily≥-5% + return_1d[-5%,29.5%)'
        )}
      </div>
    </div>
  );
};



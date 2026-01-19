import React, { useState, useEffect } from 'react';
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
  ShoppingCart,
  Banknote
} from 'lucide-react';
import { RecommendedStock } from '../types';

const API_BASE_URL = 'http://localhost:5000/api';

interface RecommendationsProps {
  onStockClick: (stock: RecommendedStock) => void;
}

type SortKey = 'probability' | 'expected_return' | 'name' | 'current_price';
type SortDirection = 'asc' | 'desc';

// AI Thinking Animation Component
const AIThinkingLoader = () => (
  <div className="flex flex-col items-center justify-center py-20 animate-in fade-in duration-700">
    <div className="relative w-24 h-24 mb-8">
      <div className="absolute inset-0 border-4 border-point-cyan/20 rounded-full animate-[spin_3s_linear_infinite]"></div>
      <div className="absolute inset-0 border-4 border-t-point-cyan rounded-full animate-[spin_1.5s_linear_infinite]"></div>
      <div className="absolute inset-4 bg-[#1a1f2e] rounded-full flex items-center justify-center border border-slate-700 shadow-[0_0_30px_rgba(6,182,212,0.3)]">
        <BrainCircuit className="w-8 h-8 text-point-cyan animate-pulse" />
      </div>
    </div>
    <h3 className="text-xl font-black text-white mb-2 tracking-tight">AI Agent가 시장을 분석 중입니다</h3>
    <p className="text-slate-500 font-medium text-center max-w-md leading-relaxed">
      기술적 지표, 수급 데이터, 재무제표를 종합하여<br/>
      <span className="text-point-cyan font-bold">상승 확률 80% 이상</span>의 초고확률 종목을 발굴하고 있습니다.
    </p>
  </div>
);

export const Recommendations: React.FC<RecommendationsProps> = ({ onStockClick }) => {
  const [recommendations, setRecommendations] = useState<RecommendedStock[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isPredicting, setIsPredicting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // 정렬 상태
  const [sortConfig, setSortConfig] = useState<{ key: SortKey; direction: SortDirection }>({
    key: 'expected_return', // 기본 정렬: 기대수익률 (기존 AI 로직과 일치)
    direction: 'desc'
  });

  const fetchRecommendations = async (refresh = false) => {
    // refresh가 true면 예측 요청 (POST), 아니면 조회 요청 (GET)
    if (refresh) {
      setIsPredicting(true);
      setError(null);
      try {
        const response = await fetch(`${API_BASE_URL}/recommendations/predict`, {
            method: 'POST'
        });
        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.error || 'Prediction failed');
        }
        // 예측 후 데이터 다시 로드
        await fetchRecommendations(false);
      } catch (err: any) {
        setError(err.message || 'AI 분석 중 오류가 발생했습니다');
        console.error(err);
      } finally {
        setIsPredicting(false);
      }
      return;
    }

    // GET 조회
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/recommendations`);
      if (response.ok) {
        const data = await response.json();
        const processed = data.map((item: any) => ({
            ...item,
            close: item.base_price || item.close, // 호환성
        }));
        setRecommendations(processed);
      } else {
        const errData = await response.json();
        setError(errData.error || 'Failed to fetch recommendations');
      }
    } catch (err) {
      setError('Connection to backend failed');
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchRecommendations(false);
  }, []);

  // 정렬 핸들러
  const handleSort = (key: SortKey) => {
    setSortConfig(prev => ({
      key,
      direction: prev.key === key && prev.direction === 'desc' ? 'asc' : 'desc'
    }));
  };

  const handleBuy = (e: React.MouseEvent, stock: RecommendedStock) => {
    e.stopPropagation();
    if (window.confirm(`[매수 확인]\n종목명: ${stock.name} (${stock.code})\n\n이 종목을 매수하시겠습니까?`)) {
      console.log(`매수 요청: ${stock.name}`);
      // TODO: 실제 매수 로직 구현
    }
  };

  const handleSell = (e: React.MouseEvent, stock: RecommendedStock) => {
    e.stopPropagation();
    if (window.confirm(`[매도 확인]\n종목명: ${stock.name} (${stock.code})\n\n이 종목을 매도하시겠습니까?`)) {
      console.log(`매도 요청: ${stock.name}`);
      // TODO: 실제 매도 로직 구현
    }
  };

  // 날짜별로 그룹핑
  const groupedRecommendations = recommendations.reduce((acc, stock) => {
      const date = stock.date || 'Unknown';
      if (!acc[date]) acc[date] = [];
      acc[date].push(stock);
      return acc;
  }, {} as Record<string, RecommendedStock[]>);

  // 날짜 내림차순 정렬
  const sortedDates = Object.keys(groupedRecommendations).sort((a, b) => new Date(b).getTime() - new Date(a).getTime());

  // 오늘 날짜 확인
  const today = new Date().toLocaleDateString('en-CA'); 

  const formatPrice = (price?: number) => {
    if (price === undefined) return '-';
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

  if (isPredicting) {
      return <AIThinkingLoader />;
  }

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-black text-white flex items-center gap-3">
            <Sparkles className="w-8 h-8 text-point-cyan" />
            AI 추천 히스토리
          </h1>
          <p className="text-slate-500 mt-2 font-medium">
            CatBoost 모델이 확률 80% 이상으로 예측한 종목들의 성과를 추적합니다.
          </p>
        </div>
        
        <button 
          onClick={() => fetchRecommendations(true)}
          disabled={isLoading || isPredicting}
          className="flex items-center gap-2 bg-slate-800 hover:bg-point-cyan hover:text-white text-slate-300 px-5 py-3 rounded-xl transition-all font-bold group"
        >
          <Cpu className={`w-5 h-5 ${isPredicting ? 'animate-spin' : 'group-hover:scale-110 transition-transform'}`} />
          AI 다시 추천받기
        </button>
      </div>

      {error && !isPredicting && (
        <div className="bg-rose-500/10 border border-rose-500/30 rounded-2xl p-6 text-center mb-8 animate-in slide-in-from-top-2">
          <p className="text-rose-400 font-bold mb-4 flex items-center justify-center gap-2">
            <AlertCircle className="w-5 h-5" />
            {error}
          </p>
          <button 
            onClick={() => fetchRecommendations(false)}
            className="bg-rose-500 hover:bg-rose-600 text-white px-6 py-2 rounded-xl transition-all font-bold text-sm"
          >
            데이터 다시 불러오기
          </button>
        </div>
      )}

      {isLoading && !isPredicting ? (
        <div className="space-y-4">
            {[1, 2, 3].map(i => (
                <div key={i} className="h-24 bg-[#1a1f2e] rounded-2xl animate-pulse" />
            ))}
        </div>
      ) : recommendations.length === 0 ? (
        <div className="bg-[#1a1f2e] border border-dashed border-slate-700 rounded-[2rem] py-32 px-10 text-center">
            <div className="w-20 h-20 bg-slate-800 rounded-full flex items-center justify-center mx-auto mb-6">
                <Search className="w-10 h-10 text-slate-500 opacity-50" />
            </div>
          <h3 className="text-xl font-bold text-white mb-2">아직 분석된 종목이 없습니다</h3>
          <p className="text-slate-500 mb-8">오른쪽 상단의 "AI 다시 추천받기" 버튼을 눌러 첫 번째 분석을 시작하세요.</p>
        </div>
      ) : (
        <div className="space-y-10 animate-in fade-in duration-500">
            {sortedDates.map(date => {
                const isToday = date === today;
                let stocks = groupedRecommendations[date];
                
                // 날짜별 섹션 내에서 정렬 적용
                stocks.sort((a, b) => {
                    let valA: any = a[sortConfig.key];
                    let valB: any = b[sortConfig.key];

                    // 특수 케이스: 현재가는 undefined일 수 있음
                    if (sortConfig.key === 'current_price') {
                        valA = a.current_price || 0;
                        valB = b.current_price || 0;
                    }

                    if (valA < valB) return sortConfig.direction === 'asc' ? -1 : 1;
                    if (valA > valB) return sortConfig.direction === 'asc' ? 1 : -1;
                    return 0;
                });
                
                return (
                    <div key={date} className="relative">
                        {/* Date Header */}
                        <div className="flex items-center gap-4 mb-4 sticy top-0 bg-[#0f121d]/80 backdrop-blur-sm py-2 z-10">
                            <div className={`px-4 py-1.5 rounded-lg text-sm font-black flex items-center gap-2 ${
                                isToday ? 'bg-point-cyan text-white shadow-lg shadow-point-cyan/20' : 'bg-slate-800 text-slate-400'
                            }`}>
                                <Calendar className="w-4 h-4" />
                                {date}
                            </div>
                            {isToday && <span className="text-point-cyan text-xs font-bold animate-pulse">● 오늘 예측 완료 (실시간 시세 반영 중)</span>}
                            <div className="h-px bg-slate-800 flex-1"></div>
                        </div>

                        {/* List View */}
                        <div className="bg-[#1a1f2e] border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
                            {/* Table Header */}
                            <div className="grid grid-cols-12 gap-4 p-4 bg-[#151925] border-b border-slate-800 text-xs font-bold text-slate-500 uppercase tracking-wider select-none">
                                <div className="col-span-1 text-center">No</div>
                                <div 
                                    className="col-span-3 pl-2 cursor-pointer hover:text-white flex items-center gap-1"
                                    onClick={() => handleSort('name')}
                                >
                                    종목명 {sortConfig.key === 'name' && <ArrowUpDown className="w-3 h-3" />}
                                </div>
                                <div className="col-span-2 text-right">추천가</div>
                                <div 
                                    className="col-span-2 text-right cursor-pointer hover:text-white flex items-center justify-end gap-1"
                                    onClick={() => handleSort('current_price')}
                                >
                                    현재가 {sortConfig.key === 'current_price' && <ArrowUpDown className="w-3 h-3" />}
                                </div>
                                <div 
                                    className="col-span-1 text-right cursor-pointer hover:text-white flex items-center justify-end gap-1"
                                    onClick={() => handleSort('probability')}
                                >
                                    확률 {sortConfig.key === 'probability' && <ArrowUpDown className="w-3 h-3" />}
                                </div>
                                <div 
                                    className="col-span-1 text-right cursor-pointer hover:text-white flex items-center justify-end gap-1"
                                    onClick={() => handleSort('expected_return')}
                                >
                                    기대수익 {sortConfig.key === 'expected_return' && <ArrowUpDown className="w-3 h-3" />}
                                </div>
                                <div className="col-span-2 text-center">주문</div>
                            </div>
                            
                            {/* Table Body */}
                            {stocks.map((stock, idx) => {
                                const returnRate = stock.return_rate || 0;
                                const isPositive = returnRate >= 0;
                                const isProfit = returnRate >= 0.5; // 0.5% 이상 수익시 강조
                                
                                return (
                                <div 
                                    key={stock.id || stock.code}
                                    onClick={() => onStockClick(stock)}
                                    className="grid grid-cols-12 gap-4 p-4 border-b border-slate-800/50 hover:bg-slate-800/50 cursor-pointer transition-colors group items-center"
                                >
                                    {/* Rank */}
                                    <div className="col-span-1 flex justify-center">
                                        <div className={`w-6 h-6 rounded flex items-center justify-center text-xs font-bold ${
                                            idx < 3 ? 'bg-point-cyan/20 text-point-cyan' : 'bg-slate-800 text-slate-500'
                                        }`}>
                                            {idx + 1}
                                        </div>
                                    </div>

                                    {/* Name & Code */}
                                    <div className="col-span-3 flex flex-col justify-center pl-2">
                                        <div className="flex items-center gap-2">
                                            <span className="text-white font-bold group-hover:text-point-cyan transition-colors truncate">{stock.name}</span>
                                            {stock.probability >= 0.9 && (
                                                <Zap className="w-3 h-3 text-yellow-400 fill-yellow-400" />
                                            )}
                                        </div>
                                        <span className="text-xs text-slate-500 font-mono">{stock.code} · {formatMarketCap(stock.market_cap)}</span>
                                    </div>

                                    {/* Base Price */}
                                    <div className="col-span-2 text-right text-slate-400 font-mono text-sm">
                                        {formatPrice(stock.base_price)}원
                                    </div>

                                    {/* Current Price & Return Rate */}
                                    <div className="col-span-2 text-right">
                                        <div className="font-mono text-sm font-bold text-white mb-0.5">
                                            {formatPrice(stock.current_price)}원
                                        </div>
                                        <div className={`text-xs font-bold ${
                                            isPositive ? 'text-emerald-400' : 'text-rose-400'
                                        }`}>
                                            {isPositive ? '+' : ''}{formatReturnRate(returnRate)}
                                        </div>
                                    </div>

                                    {/* Probability */}
                                    <div className="col-span-1 text-right">
                                        <span className="text-sm font-bold text-point-cyan">{formatPercent(stock.probability)}</span>
                                    </div>

                                    {/* Expected Return */}
                                    <div className="col-span-1 text-right">
                                        <span className="text-sm font-bold text-emerald-400">+{formatPercent(stock.expected_return)}</span>
                                    </div>

                                    {/* Action Buttons */}
                                    <div className="col-span-2 flex items-center justify-center gap-2">
                                        <button 
                                            onClick={(e) => handleSell(e, stock)}
                                            className="bg-rose-500/10 hover:bg-rose-500 text-rose-400 hover:text-white border border-rose-500/30 px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1"
                                        >
                                            <Banknote className="w-3 h-3" /> 매도
                                        </button>
                                        <button 
                                            onClick={(e) => handleBuy(e, stock)}
                                            className="bg-point-cyan/10 hover:bg-point-cyan text-point-cyan hover:text-white border border-point-cyan/30 px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1"
                                        >
                                            <ShoppingCart className="w-3 h-3" /> 매수
                                        </button>
                                    </div>
                                </div>
                                );
                            })}
                        </div>
                    </div>
                );
            })}
        </div>
      )}
    </div>
  );
};



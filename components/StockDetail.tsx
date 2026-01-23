
import React, { useState, useMemo, useEffect } from 'react';
import { StockData, StockMemo, CandleData, InvestorTrendData } from '../types';
import { Button } from './Button';
import { TradeManager } from './TradeManager';
import { 
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Cell, LineChart, Line, Legend, AreaChart, Area
} from 'recharts';
import { ArrowLeft, Plus, Calendar, Trash2, TrendingUp, TrendingDown, Clock, BarChart3, PieChart, Activity, Globe, Zap, ScrollText, CandlestickChart as CandleIcon, MousePointer2, Users2, AlertCircle, DollarSign } from 'lucide-react';

const API_BASE_URL = '/api';

// 시가총액을 한국어 단위로 변환 (예: 8조2천2백억)
const formatMarketCap = (value: string | number): string => {
  let num: number;
  if (typeof value === 'string') {
    num = parseFloat(value.replace(/,/g, ''));
  } else {
    num = value;
  }
  
  if (isNaN(num) || num === 0) return '-';
  
  if (num >= 1000000000000) {
    const jo = Math.floor(num / 1000000000000);
    const eok = Math.floor((num % 1000000000000) / 100000000);
    if (jo > 0 && eok > 0) {
      const eok1000 = Math.floor(eok / 1000);
      const eok100 = Math.floor((eok % 1000) / 100);
      let result = `${jo}조`;
      if (eok1000 > 0) result += `${eok1000}천`;
      if (eok100 > 0) result += `${eok100}백`;
      result += '억';
      return result;
    } else if (jo > 0) {
      return `${jo}조`;
    }
    return `${Math.floor(num / 100000000).toLocaleString()}억`;
  } else if (num >= 100000000) {
    return `${Math.floor(num / 100000000).toLocaleString()}억`;
  } else if (num >= 10000) {
    const jo = Math.floor(num / 10000);
    const eok = num % 10000;
    if (jo > 0) {
      const eok1000 = Math.floor(eok / 1000);
      const eok100 = Math.floor((eok % 1000) / 100);
      let result = `${jo}조`;
      if (eok1000 > 0) result += `${eok1000}천`;
      if (eok100 > 0) result += `${eok100}백`;
      if (eok1000 > 0 || eok100 > 0) result += '억';
      return result;
    }
    return `${num.toLocaleString()}억`;
  } else if (num >= 1) {
    return `${Math.floor(num).toLocaleString()}억`;
  }
  
  return '-';
};

interface StockDetailProps {
  stock: StockData;
  onBack: () => void;
  onUpdate: (updatedStock: StockData) => void;
  onDelete: (id: string) => void;
}

type TimeFrame = '15m' | 'D' | 'W' | 'M';

// 캔들차트 렌더링을 위한 커스텀 Shape
const Candlestick = (props: any) => {
  const { x, y, width, height, low, high, open, close } = props;
  const isUp = close >= open;
  const color = isUp ? '#22c55e' : '#f43f5e';

  const ratio = height / Math.max(Math.abs(open - close), 0.001);
  const wickX = x + width / 2;
  const wickHighY = y + (open > close ? 0 : height) - (high - Math.max(open, close)) * ratio;
  const wickLowY = y + (open > close ? height : 0) + (Math.min(open, close) - low) * ratio;

  return (
    <g>
      <line x1={wickX} y1={wickHighY} x2={wickX} y2={wickLowY} stroke={color} strokeWidth={1.5} />
      <rect x={x} y={y} width={width} height={Math.max(height, 1)} fill={color} />
    </g>
  );
};

// "조회안됨" 메시지 컴포넌트
const NoDataMessage: React.FC<{ message?: string }> = ({ message = "조회안됨" }) => (
  <div className="flex flex-col items-center justify-center h-full text-slate-500 py-12">
    <AlertCircle className="w-12 h-12 mb-4 text-slate-600" />
    <p className="text-lg font-bold">{message}</p>
  </div>
);

export const StockDetail: React.FC<StockDetailProps> = ({ stock, onBack, onUpdate, onDelete }) => {
  const [memoText, setMemoText] = useState('');
  const [timeFrame, setTimeFrame] = useState<TimeFrame>('D');
  
  // 실제 데이터 상태
  const [candleData, setCandleData] = useState<any[]>([]);
  const [candleLoading, setCandleLoading] = useState(true);
  const [candleError, setCandleError] = useState<string | null>(null);
  
  const [investorData, setInvestorData] = useState<any[]>([]);
  const [investorLoading, setInvestorLoading] = useState(true);
  const [investorError, setInvestorError] = useState<string | null>(null);

  // 분기별 영업이익률 데이터
  const [marginData, setMarginData] = useState<any[]>([]);
  const [marginLoading, setMarginLoading] = useState(true);
  const [marginError, setMarginError] = useState<string | null>(null);

  // 캔들 데이터 로드 (./data parquet에서)
  useEffect(() => {
    const fetchCandleData = async () => {
      setCandleLoading(true);
      setCandleError(null);
      try {
        const response = await fetch(`${API_BASE_URL}/stock-bars/${stock.symbol}?days=60`);
        const result = await response.json();
        
        if (result.success && result.data && result.data.length > 0) {
          const formatted = result.data.map((bar: any) => ({
            time: bar.time,
            date: bar.date,
            open: bar.open,
            close: bar.close,
            high: bar.high,
            low: bar.low,
            volume: bar.volume,
            display: [bar.open, bar.close]
          }));
          setCandleData(formatted);
        } else {
          setCandleError(result.error || "데이터없음");
          setCandleData([]);
        }
      } catch (e) {
        setCandleError("데이터없음");
        setCandleData([]);
      } finally {
        setCandleLoading(false);
      }
    };
    
    fetchCandleData();
  }, [stock.symbol]);

  // 투자자별 수급 데이터 로드 (KIS API 또는 네이버 금융 크롤링)
  useEffect(() => {
    const fetchInvestorData = async () => {
      setInvestorLoading(true);
      setInvestorError(null);
      try {
        // 먼저 KIS API 시도
        let response = await fetch(`${API_BASE_URL}/kis-investor-trends/${stock.symbol}`);
        let result = await response.json();
        
        // KIS API 성공시 해당 데이터 사용
        if (result.data && result.data.length > 0) {
          const formatted = result.data.map((item: any) => ({
            date: item.date ? `${item.date.slice(4,6)}/${item.date.slice(6,8)}` : '',
            외국인: item.foreignNet || 0,
            기관: item.institutionNet || 0,
            개인: item.individualNet || 0,
          })).reverse();  // 날짜 순서 정렬
          setInvestorData(formatted);
        } else {
          // KIS 실패시 네이버 크롤링 폴백
          response = await fetch(`${API_BASE_URL}/investor-trends/${stock.symbol}`);
          result = await response.json();
          
          if (result.success && result.data && result.data.length > 0) {
            const formatted = result.data.map((item: any) => ({
              date: item.date,
              외국인: item.foreign,
              기관: item.institution,
              개인: item.individual,
            }));
            setInvestorData(formatted);
          } else {
            setInvestorError(result.error || "조회안됨");
            setInvestorData([]);
          }
        }
      } catch (e) {
        setInvestorError("조회안됨");
        setInvestorData([]);
      } finally {
        setInvestorLoading(false);
      }
    };
    
    fetchInvestorData();
  }, [stock.symbol]);

  // 분기별 영업이익률 데이터 로드 (KIS 손익계산서 API)
  useEffect(() => {
    const fetchMarginData = async () => {
      setMarginLoading(true);
      setMarginError(null);
      try {
        const response = await fetch(`${API_BASE_URL}/income-statement/${stock.symbol}?period=1`);
        const result = await response.json();
        
        if (result.data && result.data.length > 0) {
          // 분기별 영업이익률 데이터로 변환
          const formatted = result.data.slice(0, 8).map((item: any) => {
            // 기간을 읽기 쉬운 형식으로 변환 (202312 -> 23Q4)
            const period = item.period || '';
            const year = period.slice(2, 4);
            const month = parseInt(period.slice(4, 6));
            const quarter = Math.ceil(month / 3);
            
            return {
              quarter: `${year}Q${quarter}`,
              margin: item.operatingMargin || 0,
              sales: item.sales || 0,
              operatingProfit: item.operatingProfit || 0,
            };
          }).reverse();  // 시간순 정렬
          
          setMarginData(formatted);
        } else {
          setMarginError(result.message || "조회안됨");
          setMarginData([]);
        }
      } catch (e) {
        setMarginError("조회안됨");
        setMarginData([]);
      } finally {
        setMarginLoading(false);
      }
    };
    
    fetchMarginData();
  }, [stock.symbol]);

  // 타임프레임에 따른 캔들 데이터 필터링
  const filteredCandleData = useMemo(() => {
    if (!candleData.length) return [];
    
    if (timeFrame === 'D') {
      return candleData;
    } else if (timeFrame === 'W') {
      // 주봉: 7일 단위로 그룹화
      const weekly: any[] = [];
      for (let i = 0; i < candleData.length; i += 5) {
        const chunk = candleData.slice(i, i + 5);
        if (chunk.length === 0) continue;
        weekly.push({
          time: chunk[0].time,
          open: chunk[0].open,
          close: chunk[chunk.length - 1].close,
          high: Math.max(...chunk.map(c => c.high)),
          low: Math.min(...chunk.map(c => c.low)),
          display: [chunk[0].open, chunk[chunk.length - 1].close]
        });
      }
      return weekly;
    } else if (timeFrame === 'M') {
      // 월봉: 20일 단위로 그룹화
      const monthly: any[] = [];
      for (let i = 0; i < candleData.length; i += 20) {
        const chunk = candleData.slice(i, i + 20);
        if (chunk.length === 0) continue;
        monthly.push({
          time: chunk[0].time,
          open: chunk[0].open,
          close: chunk[chunk.length - 1].close,
          high: Math.max(...chunk.map(c => c.high)),
          low: Math.min(...chunk.map(c => c.low)),
          display: [chunk[0].open, chunk[chunk.length - 1].close]
        });
      }
      return monthly;
    }
    return candleData;
  }, [candleData, timeFrame]);

  // 가상의 캔들 데이터 생성 - 제거됨 (실제 데이터 사용)

  const handleAddMemo = async () => {
    if (!memoText.trim()) return;
    
    try {
      const response = await fetch(`${API_BASE_URL}/stocks/${stock.id}/memos`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          content: memoText
        })
      });

      if (response.ok) {
        const result = await response.json();
        const newMemo: StockMemo = {
          id: result.memo.id,
          date: result.memo.created_at,
          content: result.memo.content,
        };
        onUpdate({
          ...stock,
          memos: [newMemo, ...stock.memos]
        });
        setMemoText('');
      } else {
        console.error('메모 추가 실패');
        alert('메모 추가에 실패했습니다.');
      }
    } catch (error) {
      console.error('API 호출 실패:', error);
      alert('서버 연결에 실패했습니다.');
    }
  };

  const handleDeleteMemo = async (memoId: string) => {
    try {
      const response = await fetch(`${API_BASE_URL}/memos/${memoId}`, {
        method: 'DELETE'
      });

      if (response.ok) {
        onUpdate({
          ...stock,
          memos: stock.memos.filter(m => m.id !== memoId)
        });
      } else {
        console.error('메모 삭제 실패');
        alert('메모 삭제에 실패했습니다.');
      }
    } catch (error) {
      console.error('API 호출 실패:', error);
      alert('서버 연결에 실패했습니다.');
    }
  };

  const daysSinceAdded = Math.floor((Date.now() - new Date(stock.addedAt).getTime()) / (1000 * 60 * 60 * 24));

  const [showTradeModal, setShowTradeModal] = useState(false);

  return (
    <div className="animate-in fade-in slide-in-from-bottom-6 duration-700 pb-20">
      <div className="flex items-center justify-between mb-8">
        <button 
          onClick={onBack}
          className="flex items-center text-slate-400 hover:text-point-cyan transition-all font-bold group"
        >
          <div className="w-10 h-10 rounded-full bg-slate-800 flex items-center justify-center mr-3 group-hover:bg-point-cyan transition-colors">
            <ArrowLeft className="w-5 h-5 text-white" />
          </div>
          목록으로 돌아가기
        </button>
        <div className="flex items-center gap-3">
          <Button variant="primary" size="sm" onClick={() => setShowTradeModal(true)}>
            <Plus className="w-4 h-4 mr-2" /> 거래 추가
          </Button>
          <Button variant="danger" size="sm" onClick={() => onDelete(stock.id)}>
            <Trash2 className="w-4 h-4 mr-2" /> 분석 종료 및 삭제
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-8">
          {/* 상단 기본 정보 카드 */}
          <div className="card-flat rounded-3xl p-8 shadow-2xl relative overflow-hidden">
            <div className="flex flex-wrap justify-between items-start gap-6 mb-8 relative z-10">
              <div>
                <div className="flex items-center gap-4 mb-3">
                  <h1 className="text-4xl font-black text-white tracking-tighter">{stock.name}</h1>
                  <span className="bg-point-cyan text-white px-3 py-1 rounded-xl text-xs font-black">{stock.symbol}</span>
                </div>
                {/* 현재가 및 등락률 */}
                <div className="flex items-center gap-4 mb-3">
                  <span className="text-3xl font-black text-white">{(stock.currentPrice || 0).toLocaleString()}원</span>
                  <span className={`flex items-center gap-1 text-lg font-bold ${(stock.changePercent || 0) >= 0 ? 'text-rose-400' : 'text-blue-400'}`}>
                    {(stock.changePercent || 0) >= 0 ? <TrendingUp className="w-5 h-5" /> : <TrendingDown className="w-5 h-5" />}
                    {(stock.changePercent || 0) >= 0 ? '+' : ''}{(stock.changePercent || 0).toFixed(2)}%
                    <span className="text-sm">({(stock.change || 0) >= 0 ? '+' : ''}{(stock.change || 0).toLocaleString()})</span>
                  </span>
                </div>
                <div className="flex items-center text-slate-400 text-xs font-bold bg-[#0f121d] px-3 py-1.5 rounded-full w-fit border border-slate-700/50">
                  <Clock className="w-3.5 h-3.5 mr-2 text-point-cyan" />
                  <span>{new Date(stock.addedAt).toLocaleDateString()} 발견 · {daysSinceAdded === 0 ? '오늘 발견' : `${daysSinceAdded}일차`}</span>
                </div>
              </div>
              <div className="text-right">
                <p className="text-[10px] text-point-orange uppercase font-black mb-1 tracking-[0.2em]">시총</p>
                <p className="text-3xl font-black text-white">{formatMarketCap(stock.marketCap)}</p>
              </div>
            </div>

            {/* 주요 지표 그리드 */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8 relative z-10">
              <div className="bg-[#0f121d] border border-slate-700 p-4 rounded-2xl cursor-help group/tip" title="주가수익비율: 주가 / 주당순이익(EPS). 낮을수록 저평가 상태로 간주되지만 업종 평균과 비교가 필요합니다.">
                <div className="flex items-center gap-2 mb-1">
                  <Activity className="w-3.5 h-3.5 text-point-yellow" />
                  <span className="text-[9px] text-slate-500 font-black uppercase">PER</span>
                </div>
                <p className="text-xl font-black text-white">{stock.per}</p>
              </div>
              <div className="bg-[#0f121d] border border-slate-700 p-4 rounded-2xl cursor-help group/tip" title="주가순자산비율: 주가 / 주당순자산가치(BPS). 1미만이면 주가가 장부상 순자산가치에도 못 미치는 저평가 상태입니다.">
                <div className="flex items-center gap-2 mb-1">
                  <BarChart3 className="w-3.5 h-3.5 text-point-green" />
                  <span className="text-[9px] text-slate-500 font-black uppercase">PBR</span>
                </div>
                <p className="text-xl font-black text-white">{stock.pbr}</p>
              </div>
              <div className="bg-[#0f121d] border border-slate-700 p-4 rounded-2xl cursor-help group/tip" title="주당순이익: 당기순이익 / 발행주식수. 기업이 1주당 얼마의 수익을 창출했는지를 나타내는 지표입니다.">
                <div className="flex items-center gap-2 mb-1">
                  <Zap className="w-3.5 h-3.5 text-point-orange" />
                  <span className="text-[9px] text-slate-500 font-black uppercase">EPS</span>
                </div>
                <p className="text-xl font-black text-white">{stock.eps.toLocaleString()}</p>
              </div>
              <div className="bg-[#0f121d] border border-slate-700 p-4 rounded-2xl cursor-help group/tip" title="외국인 보유 비중: 외국인 투자자가 해당 기업의 주식을 얼마나 보유하고 있는지 나타냅니다.">
                <div className="flex items-center gap-2 mb-1">
                  <Globe className="w-3.5 h-3.5 text-point-cyan" />
                  <span className="text-[9px] text-slate-500 font-black uppercase">Foreign</span>
                </div>
                <p className="text-xl font-black text-point-cyan">{stock.foreignOwnership}%</p>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 py-6 border-t border-slate-700/50 relative z-10 text-[11px]">
              <div className="bg-[#0f121d]/50 p-3 rounded-xl border border-slate-800 cursor-help" title="당일 거래된 주식 수와 거래 총액입니다.">
                <p className="text-slate-500 font-black mb-1 uppercase tracking-wider">거래 유동성</p>
                <p className="font-extrabold text-slate-200">{stock.tradingVolume} / {stock.transactionAmount}</p>
              </div>
              <div className="bg-[#0f121d]/50 p-3 rounded-xl border border-slate-800 cursor-help" title="시장에서 실제 매매가 가능한 주식 수 비중입니다.">
                <p className="text-slate-500 font-black mb-1 uppercase tracking-wider">유통량</p>
                <p className="font-extrabold text-slate-200">{stock.floatingShares}</p>
              </div>
              <div className="bg-[#0f121d]/50 p-3 rounded-xl border border-slate-800 cursor-help" title="최대주주 및 특수관계인의 지분율로, 경영권 안정 수준을 파악할 수 있습니다.">
                <p className="text-slate-500 font-black mb-1 uppercase tracking-wider">최대주주</p>
                <p className="font-extrabold text-slate-200">{stock.majorShareholderStake}%</p>
              </div>
            </div>
          </div>

          {/* 매수/매도 관리 - 두 번째 위치 */}
          <TradeManager 
            stockId={stock.id} 
            stockSymbol={stock.symbol} 
            stockName={stock.name} 
            initialOpen={showTradeModal}
            onFormClose={() => setShowTradeModal(false)}
          />

          {/* 캔들 차트 분석 */}
          <div className="bg-[#1a1f2e] p-8 rounded-[2.5rem] border border-slate-700/50 shadow-2xl relative overflow-hidden">
            <div className="flex flex-wrap items-center justify-between mb-8 gap-6">
              <div className="flex items-center gap-4">
                <div className="p-2.5 bg-point-cyan/10 rounded-xl border border-point-cyan/20">
                  <CandleIcon className="w-6 h-6 text-point-cyan" />
                </div>
                <div>
                  <h3 className="text-sm font-black text-white uppercase tracking-widest">실시간 캔들 차트</h3>
                  <p className="text-[10px] text-slate-500 font-bold">봉차트 분석 및 가격 흐름</p>
                </div>
              </div>
              <div className="flex bg-[#0f121d] p-1.5 rounded-2xl border border-slate-700 shadow-inner">
                {(['15m', 'D', 'W', 'M'] as TimeFrame[]).map((tf) => (
                  <button
                    key={tf}
                    onClick={() => setTimeFrame(tf)}
                    className={`px-4 py-2 text-[11px] font-black rounded-xl transition-all ${
                      timeFrame === tf ? 'bg-point-cyan text-white shadow-lg' : 'text-slate-500 hover:text-slate-300'
                    }`}
                  >
                    {tf === '15m' ? '15분' : tf === 'D' ? '일봉' : tf === 'W' ? '주봉' : '월봉'}
                  </button>
                ))}
              </div>
            </div>

            <div className="h-64 w-full overflow-x-auto custom-scrollbar">
              {candleLoading ? (
                <div className="flex items-center justify-center h-full text-slate-500">
                  <p className="font-bold">로딩 중...</p>
                </div>
              ) : candleError || filteredCandleData.length === 0 ? (
                <NoDataMessage message={candleError || "데이터없음"} />
              ) : (
                <div style={{ minWidth: '800px', width: '100%', height: '256px' }}>
                  <ResponsiveContainer width="100%" height={256}>
                    <BarChart data={filteredCandleData} barGap={0}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#2d3446" />
                      <XAxis dataKey="time" axisLine={false} tickLine={false} tick={{fill: '#475569', fontSize: 10, fontWeight: 700}} dy={15} />
                      <YAxis domain={['auto', 'auto']} orientation="right" axisLine={false} tickLine={false} tick={{fill: '#475569', fontSize: 10, fontWeight: 700}} />
                      <Tooltip contentStyle={{backgroundColor: '#0f121d', borderRadius: '12px', border: '1px solid #334155', fontSize: '11px'}} />
                      <Bar dataKey="display" shape={<Candlestick />} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </div>

          {/* 수급 및 실적 심층 분석 섹션 - 한 행에 한 가지씩 */}
          <div className="space-y-8">
            {/* 분기별 영업이익률 추이 */}
            <div className="bg-[#1a1f2e] p-8 rounded-[2.5rem] border border-slate-700/50 shadow-2xl">
              <div className="flex items-center gap-3 mb-6">
                <DollarSign className="w-6 h-6 text-point-green" />
                <h3 className="text-sm font-black text-white uppercase tracking-widest">분기별 영업이익률</h3>
              </div>
              <div className="h-64 w-full">
                {marginLoading ? (
                  <div className="flex items-center justify-center h-full text-slate-500">
                    <p className="font-bold">로딩 중...</p>
                  </div>
                ) : marginError || marginData.length === 0 ? (
                  <NoDataMessage message={marginError || "조회안됨"} />
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={marginData}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#2d3446" />
                      <XAxis dataKey="quarter" axisLine={false} tickLine={false} tick={{fill: '#475569', fontSize: 10}} />
                      <YAxis axisLine={false} tickLine={false} tick={{fill: '#475569', fontSize: 10}} tickFormatter={(v) => `${v}%`} />
                      <Tooltip 
                        contentStyle={{backgroundColor: '#0f121d', borderRadius: '12px', border: '1px solid #334155', fontSize: '11px'}}
                        formatter={(value: number, name: string) => {
                          if (name === 'margin') return [`${value.toFixed(2)}%`, '영업이익률'];
                          return [value, name];
                        }}
                      />
                      <Bar dataKey="margin" name="영업이익률" radius={[6, 6, 0, 0]}>
                        {marginData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.margin >= 0 ? '#22c55e' : '#f43f5e'} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </div>

            {/* 수급 현황 (외국인, 기관, 개인) */}
            <div className="bg-[#1a1f2e] p-8 rounded-[2.5rem] border border-slate-700/50 shadow-2xl">
              <div className="flex items-center gap-3 mb-6">
                <Users2 className="w-6 h-6 text-point-cyan" />
                <h3 className="text-sm font-black text-white uppercase tracking-widest">일자별 수급 현황</h3>
              </div>
              <div className="h-64 w-full">
                {investorLoading ? (
                  <div className="flex items-center justify-center h-full text-slate-500">
                    <p className="font-bold">로딩 중...</p>
                  </div>
                ) : investorError || investorData.length === 0 ? (
                  <NoDataMessage message={investorError || "조회안됨"} />
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={investorData}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#2d3446" />
                      <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{fill: '#475569', fontSize: 10}} />
                      <YAxis hide />
                      <Tooltip 
                        contentStyle={{backgroundColor: '#0f121d', borderRadius: '12px', border: '1px solid #334155', fontSize: '11px'}}
                      />
                      <Legend iconType="circle" wrapperStyle={{fontSize: '11px', fontWeight: 700, paddingTop: '10px'}} />
                      <Line type="monotone" dataKey="외국인" stroke="#06b6d4" strokeWidth={3} dot={false} />
                      <Line type="monotone" dataKey="기관" stroke="#f97316" strokeWidth={3} dot={false} />
                      <Line type="monotone" dataKey="개인" stroke="#facc15" strokeWidth={3} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </div>
            </div>
          </div>

          {/* 일지 입력 영역 */}
          <div className="card-flat rounded-3xl p-10 shadow-xl">
            <h3 className="text-2xl font-black text-white mb-8 flex items-center">
              <ScrollText className="w-7 h-7 mr-4 text-point-yellow" />
              오늘의 종목 분석 일지
            </h3>
            <textarea
              className="w-full h-40 p-6 border border-slate-700 rounded-2xl focus:ring-2 focus:ring-point-cyan focus:border-point-cyan resize-none bg-[#0f121d] text-white transition-all placeholder-slate-600 font-bold leading-relaxed shadow-inner"
              placeholder="수급의 변화, 차트 상의 특이점, 실적 전망 등을 자유롭게 기록하세요..."
              value={memoText}
              onChange={(e) => setMemoText(e.target.value)}
            />
            <div className="flex justify-end mt-6">
              <Button onClick={handleAddMemo} disabled={!memoText.trim()} variant="success" size="lg" className="px-12 shadow-lg shadow-point-green/20">
                기록 저장하기
              </Button>
            </div>
          </div>
        </div>

        {/* 사이드바 히스토리 */}
        <div className="space-y-8">
          <div className="flex items-center justify-between px-4">
            <h3 className="text-2xl font-black text-white flex items-center tracking-tight">
              <Calendar className="w-6 h-6 mr-3 text-point-orange" />
              히스토리
            </h3>
            <span className="bg-[#1a1f2e] text-point-cyan text-[11px] font-black px-3 py-1.5 rounded-full border border-slate-700">{stock.memos.length} ANALYSES</span>
          </div>
          
          <div className="space-y-5 max-h-[1200px] overflow-y-auto pr-3 custom-scrollbar">
            {stock.memos.length === 0 && (
              <div className="text-center py-24 bg-[#1a1f2e]/50 rounded-2xl border border-dashed border-slate-700">
                <ScrollText className="w-12 h-12 text-slate-700 mx-auto mb-4" />
                <p className="text-slate-500 font-extrabold italic">아직 기록된 분석이 없습니다.</p>
              </div>
            )}
            {stock.memos.map((memo) => (
              <div key={memo.id} className="card-flat p-8 rounded-2xl shadow-lg relative group hover:border-point-cyan transition-all">
                <button 
                  onClick={() => handleDeleteMemo(memo.id)}
                  className="absolute top-8 right-8 text-slate-700 hover:text-rose-400 opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <Trash2 className="w-5 h-5" />
                </button>
                <div className="text-[11px] text-point-cyan font-black mb-4 flex items-center gap-3">
                  <div className="w-2.5 h-2.5 rounded-full bg-point-cyan shadow-[0_0_10px_rgba(6,182,212,0.5)]"></div>
                  {new Date(memo.date).toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'short' })}
                </div>
                <div className="text-slate-300 whitespace-pre-wrap leading-loose text-sm font-bold tracking-tight">
                  {memo.content}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

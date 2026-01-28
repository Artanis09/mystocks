
import React, { useState, useMemo, useEffect, useRef } from 'react';
import { StockData, StockMemo, CandleData, InvestorTrendData } from '../types';
import { Button } from './Button';
import { TradeManager } from './TradeManager';
import { 
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Cell, LineChart, Line, Legend, AreaChart, Area
} from 'recharts';
import { createChart, ColorType, IChartApi, ISeriesApi } from 'lightweight-charts';
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
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candlestickSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  
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

  // 타임프레임에 따른 캔들 데이터 필터링
  const filteredCandleData = useMemo(() => {
    if (!candleData.length) return [];
    
    if (timeFrame === 'D') {
      return candleData;
    } else if (timeFrame === 'W') {
      // 주봉: 5거래일 단위로 그룹화 (한국 시장)
      const weekly: any[] = [];
      for (let i = 0; i < candleData.length; i += 5) {
        const chunk = candleData.slice(i, i + 5);
        if (chunk.length === 0) continue;
        weekly.push({
          date: chunk[0].date,
          open: chunk[0].open,
          close: chunk[chunk.length - 1].close,
          high: Math.max(...chunk.map(c => c.high)),
          low: Math.min(...chunk.map(c => c.low)),
          volume: chunk.reduce((sum, c) => sum + (c.volume || 0), 0)
        });
      }
      return weekly;
    } else if (timeFrame === 'M') {
      // 월봉: 20거래일 단위로 그룹화
      const monthly: any[] = [];
      for (let i = 0; i < candleData.length; i += 20) {
        const chunk = candleData.slice(i, i + 20);
        if (chunk.length === 0) continue;
        monthly.push({
          date: chunk[0].date,
          open: chunk[0].open,
          close: chunk[chunk.length - 1].close,
          high: Math.max(...chunk.map(c => c.high)),
          low: Math.min(...chunk.map(c => c.low)),
          volume: chunk.reduce((sum, c) => sum + (c.volume || 0), 0)
        });
      }
      return monthly;
    }
    return candleData;
  }, [candleData, timeFrame]);

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

  // Lightweight Charts 초기화 및 업데이트
  useEffect(() => {
    if (!chartContainerRef.current) return;

    // 차트 생성
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#1a1f2e' },
        textColor: '#94a3b8',
      },
      grid: {
        vertLines: { color: '#2d3446' },
        horzLines: { color: '#2d3446' },
      },
      width: chartContainerRef.current.clientWidth,
      height: 300,
      timeScale: {
        borderColor: '#2d3446',
        timeVisible: true,
      },
      rightPriceScale: {
        borderColor: '#2d3446',
      },
      crosshair: {
        mode: 0,
        vertLine: {
          color: '#06b6d4',
          width: 0.5,
          style: 1,
          labelBackgroundColor: '#06b6d4',
        },
        horzLine: {
          color: '#06b6d4',
          width: 0.5,
          style: 1,
          labelBackgroundColor: '#06b6d4',
        },
      },
    });

    const candlestickSeries = chart.addCandlestickSeries({
      upColor: '#f43f5e', // 한국 스타일: 상승(빨강)
      downColor: '#3b82f6', // 한국 스타일: 하락(파란색)
      borderVisible: false,
      wickUpColor: '#f43f5e',
      wickDownColor: '#3b82f6',
    });

    const volumeSeries = chart.addHistogramSeries({
      color: '#334155',
      priceFormat: {
        type: 'volume',
      },
      priceScaleId: '', // overlay
    });

    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.8,
        bottom: 0,
      },
    });

    chartRef.current = chart;
    candlestickSeriesRef.current = candlestickSeries;
    volumeSeriesRef.current = volumeSeries;

    // 반응형 처리
    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, []);

  // 데이터 업데이트
  useEffect(() => {
    if (candlestickSeriesRef.current && volumeSeriesRef.current && filteredCandleData.length > 0) {
      const formattedCandles = filteredCandleData.map(d => ({
        time: d.date,
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close,
      }));

      const formattedVolume = filteredCandleData.map(d => ({
        time: d.date,
        value: d.volume || 0,
        color: d.close >= d.open ? '#f43f5ecc' : '#3b82f6cc',
      }));

      candlestickSeriesRef.current.setData(formattedCandles);
      volumeSeriesRef.current.setData(formattedVolume);

      // 최신 데이터로 이동
      chartRef.current?.timeScale().fitContent();
    }
  }, [filteredCandleData]);

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
  const [isChartMounted, setIsChartMounted] = useState(false);

  useEffect(() => {
    // Recharts sizing issue resolution: Wait for mount and a small delay for DOM layout
    const timer = setTimeout(() => {
      setIsChartMounted(true);
    }, 100);
    return () => clearTimeout(timer);
  }, []);

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

      <div className="space-y-10">
        <div className="space-y-10">
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
              <div className="bg-[#0f121d] border border-slate-700 p-4 rounded-2xl cursor-help group/tip" title="현재 주가입니다.">
                <div className="flex items-center gap-2 mb-1">
                  <DollarSign className="w-3.5 h-3.5 text-point-yellow" />
                  <span className="text-[9px] text-slate-500 font-black uppercase">현재가</span>
                </div>
                <p className="text-xl font-black text-white">{(stock.currentPrice || 0).toLocaleString()}원</p>
              </div>
              <div className="bg-[#0f121d] border border-slate-700 p-4 rounded-2xl cursor-help group/tip" title="전일 종가 대비 등락률입니다.">
                <div className="flex items-center gap-2 mb-1">
                  {(stock.changePercent || 0) >= 0 ? <TrendingUp className="w-3.5 h-3.5 text-rose-400" /> : <TrendingDown className="w-3.5 h-3.5 text-blue-400" />}
                  <span className="text-[9px] text-slate-500 font-black uppercase">당일 상승률</span>
                </div>
                <p className={`text-xl font-black ${(stock.changePercent || 0) >= 0 ? 'text-rose-400' : 'text-blue-400'}`}>
                  {(stock.changePercent || 0) >= 0 ? '+' : ''}{(stock.changePercent || 0).toFixed(2)}%
                </p>
              </div>
              <div className="bg-[#0f121d] border border-slate-700 p-4 rounded-2xl cursor-help group/tip" title="시가총액: 발행 주식 수 × 현재 주가입니다.">
                <div className="flex items-center gap-2 mb-1">
                  <BarChart3 className="w-3.5 h-3.5 text-point-orange" />
                  <span className="text-[9px] text-slate-500 font-black uppercase">시총</span>
                </div>
                <p className="text-xl font-black text-white">{formatMarketCap(stock.marketCap)}</p>
              </div>
              <div className="bg-[#0f121d] border border-slate-700 p-4 rounded-2xl cursor-help group/tip" title="전 거래일 대비 거래량 비율입니다. 100% 이상이면 전일보다 거래량이 많습니다.">
                <div className="flex items-center gap-2 mb-1">
                  <Activity className="w-3.5 h-3.5 text-point-cyan" />
                  <span className="text-[9px] text-slate-500 font-black uppercase">거래량 비율</span>
                </div>
                <p className={`text-xl font-black ${(stock.volumeRatio || 0) >= 100 ? 'text-point-cyan' : 'text-slate-400'}`}>
                  {(stock.volumeRatio || 0).toFixed(0)}%
                </p>
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

          {/* 수급 및 실적 심층 분석 섹션 - 상단 배치 */}
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
                  isChartMounted && (
                    <ResponsiveContainer width="100%" height={256} minWidth={0}>
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
                  )
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
                  isChartMounted && (
                    <ResponsiveContainer width="100%" height={256} minWidth={0}>
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
                  )
                )}
              </div>
            </div>
          </div>

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

            <div className="h-[300px] w-full relative">
              {candleLoading && (
                <div className="absolute inset-0 flex items-center justify-center bg-[#1a1f2e]/50 z-10 text-slate-500">
                  <p className="font-bold text-sm text-point-cyan animate-pulse">차트 데이터를 불러오는 중...</p>
                </div>
              )}
              {candleError || (candleData.length === 0 && !candleLoading) ? (
                <NoDataMessage message={candleError || "데이터없음"} />
              ) : (
                <div ref={chartContainerRef} className="w-full h-full rounded-xl overflow-hidden shadow-inner border border-slate-700/30" />
              )}
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

          {/* 히스토리 관리 섹션 - 맨 아래로 이동 */}
          <div className="space-y-8 pt-8 border-t border-slate-800">
            <div className="flex items-center justify-between px-4">
              <h3 className="text-2xl font-black text-white flex items-center tracking-tight">
                <Calendar className="w-6 h-6 mr-3 text-point-orange" />
                분석 히스토리
              </h3>
              <span className="bg-[#1a1f2e] text-point-cyan text-[11px] font-black px-3 py-1.5 rounded-full border border-slate-700">{stock.memos.length} ANALYSES</span>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5 overflow-y-auto pr-3 custom-scrollbar">
              {stock.memos.length === 0 && (
                <div className="md:col-span-2 text-center py-24 bg-[#1a1f2e]/50 rounded-2xl border border-dashed border-slate-700">
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
    </div>
  );
};

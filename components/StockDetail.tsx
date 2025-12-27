
import React, { useState, useMemo } from 'react';
import { StockData, StockMemo } from '../types';
import { Button } from './Button';
import { 
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Cell, LineChart, Line, Legend, AreaChart, Area
} from 'recharts';
import { ArrowLeft, Plus, Calendar, Trash2, TrendingUp, Clock, BarChart3, PieChart, Activity, Globe, Zap, ScrollText, CandlestickChart as CandleIcon, MousePointer2, Users2 } from 'lucide-react';

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

export const StockDetail: React.FC<StockDetailProps> = ({ stock, onBack, onUpdate, onDelete }) => {
  const [memoText, setMemoText] = useState('');
  const [timeFrame, setTimeFrame] = useState<TimeFrame>('D');

  // 가상의 캔들 데이터 생성
  const candleData = useMemo(() => {
    const seed = stock.symbol.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
    const data = [];
    let prevClose = stock.currentPrice || 50000;
    const points = 40;
    
    for (let i = points; i >= 0; i--) {
      const volatility = prevClose * 0.03;
      const open = prevClose + (Math.random() - 0.5) * volatility;
      const close = open + (Math.random() - 0.5) * volatility;
      const high = Math.max(open, close) + Math.random() * (volatility * 0.5);
      const low = Math.min(open, close) - Math.random() * (volatility * 0.5);
      
      const date = new Date();
      if (timeFrame === '15m') date.setMinutes(date.getMinutes() - i * 15);
      else if (timeFrame === 'D') date.setDate(date.getDate() - i);
      else if (timeFrame === 'W') date.setDate(date.getDate() - i * 7);
      else if (timeFrame === 'M') date.setMonth(date.getMonth() - i);

      data.push({
        time: timeFrame === '15m' 
          ? date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
          : date.toLocaleDateString([], { month: 'short', day: 'numeric' }),
        open: Math.round(open),
        close: Math.round(close),
        high: Math.round(high),
        low: Math.round(low),
        display: [Math.round(open), Math.round(close)]
      });
      prevClose = close;
    }
    return data;
  }, [stock.symbol, stock.currentPrice, timeFrame]);

  // 가상의 수급 데이터 생성 (외국인, 기관, 개인)
  const supplyDemandData = useMemo(() => {
    const seed = stock.symbol.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0) + 99;
    const data = [];
    const points = 20;
    
    let foreignAcc = 0;
    let institutionAcc = 0;
    let individualAcc = 0;

    for (let i = points; i >= 0; i--) {
      const date = new Date();
      date.setDate(date.getDate() - i);
      
      const fChange = (Math.sin(i * 0.5 + seed) * 5000) + (Math.random() - 0.5) * 2000;
      const iChange = (Math.cos(i * 0.3 + seed) * 4000) + (Math.random() - 0.5) * 1500;
      const pChange = -(fChange + iChange); // 제로섬 가정

      foreignAcc += fChange;
      institutionAcc += iChange;
      individualAcc += pChange;

      data.push({
        date: date.toLocaleDateString([], { month: 'short', day: 'numeric' }),
        외국인: Math.round(foreignAcc),
        기관: Math.round(institutionAcc),
        개인: Math.round(individualAcc),
      });
    }
    return data;
  }, [stock.symbol]);

  const handleAddMemo = () => {
    if (!memoText.trim()) return;
    const newMemo: StockMemo = {
      id: Date.now().toString(),
      date: new Date().toISOString(),
      content: memoText,
    };
    onUpdate({
      ...stock,
      memos: [newMemo, ...stock.memos]
    });
    setMemoText('');
  };

  const handleDeleteMemo = (memoId: string) => {
    onUpdate({
      ...stock,
      memos: stock.memos.filter(m => m.id !== memoId)
    });
  };

  const daysSinceAdded = Math.floor((Date.now() - new Date(stock.addedAt).getTime()) / (1000 * 60 * 60 * 24));

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
        <Button variant="danger" size="sm" onClick={() => onDelete(stock.id)}>
          <Trash2 className="w-4 h-4 mr-2" /> 분석 종료 및 삭제
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-8">
          {/* 상단 기본 정보 카드 */}
          <div className="card-flat rounded-3xl p-8 shadow-2xl relative overflow-hidden">
            <div className="flex flex-wrap justify-between items-end gap-6 mb-8 relative z-10">
              <div>
                <div className="flex items-center gap-4 mb-3">
                  <h1 className="text-4xl font-black text-white tracking-tighter">{stock.name}</h1>
                  <span className="bg-point-cyan text-white px-3 py-1 rounded-xl text-xs font-black">{stock.symbol}</span>
                </div>
                <div className="flex items-center text-slate-400 text-xs font-bold bg-[#0f121d] px-3 py-1.5 rounded-full w-fit border border-slate-700/50">
                  <Clock className="w-3.5 h-3.5 mr-2 text-point-cyan" />
                  <span>{new Date(stock.addedAt).toLocaleDateString()} 발견 · {daysSinceAdded === 0 ? '오늘 발견' : `${daysSinceAdded}일차`}</span>
                </div>
              </div>
              <div className="text-right">
                <p className="text-[10px] text-point-orange uppercase font-black mb-1 tracking-[0.2em]">Market Cap</p>
                <p className="text-3xl font-black text-white">{stock.marketCap}</p>
              </div>
            </div>

            {/* 주요 지표 그리드 */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8 relative z-10">
              <div className="bg-[#0f121d] border border-slate-700 p-4 rounded-2xl">
                <div className="flex items-center gap-2 mb-1">
                  <Activity className="w-3.5 h-3.5 text-point-yellow" />
                  <span className="text-[9px] text-slate-500 font-black uppercase">PER</span>
                </div>
                <p className="text-xl font-black text-white">{stock.per}</p>
              </div>
              <div className="bg-[#0f121d] border border-slate-700 p-4 rounded-2xl">
                <div className="flex items-center gap-2 mb-1">
                  <BarChart3 className="w-3.5 h-3.5 text-point-green" />
                  <span className="text-[9px] text-slate-500 font-black uppercase">PBR</span>
                </div>
                <p className="text-xl font-black text-white">{stock.pbr}</p>
              </div>
              <div className="bg-[#0f121d] border border-slate-700 p-4 rounded-2xl">
                <div className="flex items-center gap-2 mb-1">
                  <Zap className="w-3.5 h-3.5 text-point-orange" />
                  <span className="text-[9px] text-slate-500 font-black uppercase">EPS</span>
                </div>
                <p className="text-xl font-black text-white">{stock.eps.toLocaleString()}</p>
              </div>
              <div className="bg-[#0f121d] border border-slate-700 p-4 rounded-2xl">
                <div className="flex items-center gap-2 mb-1">
                  <Globe className="w-3.5 h-3.5 text-point-cyan" />
                  <span className="text-[9px] text-slate-500 font-black uppercase">Foreign</span>
                </div>
                <p className="text-xl font-black text-point-cyan">{stock.foreignOwnership}%</p>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 py-6 border-t border-slate-700/50 relative z-10 text-[11px]">
              <div className="bg-[#0f121d]/50 p-3 rounded-xl border border-slate-800">
                <p className="text-slate-500 font-black mb-1 uppercase tracking-wider">거래 유동성</p>
                <p className="font-extrabold text-slate-200">{stock.tradingVolume} / {stock.transactionAmount}</p>
              </div>
              <div className="bg-[#0f121d]/50 p-3 rounded-xl border border-slate-800">
                <p className="text-slate-500 font-black mb-1 uppercase tracking-wider">유통량</p>
                <p className="font-extrabold text-slate-200">{stock.floatingShares}</p>
              </div>
              <div className="bg-[#0f121d]/50 p-3 rounded-xl border border-slate-800">
                <p className="text-slate-500 font-black mb-1 uppercase tracking-wider">최대주주</p>
                <p className="font-extrabold text-slate-200">{stock.majorShareholderStake}%</p>
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

            <div className="h-64 w-full overflow-x-auto custom-scrollbar">
              <div className="min-w-[800px] h-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={candleData} barGap={0}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#2d3446" />
                    <XAxis dataKey="time" axisLine={false} tickLine={false} tick={{fill: '#475569', fontSize: 10, fontWeight: 700}} dy={15} />
                    <YAxis domain={['auto', 'auto']} orientation="right" axisLine={false} tickLine={false} tick={{fill: '#475569', fontSize: 10, fontWeight: 700}} />
                    <Tooltip contentStyle={{backgroundColor: '#0f121d', borderRadius: '12px', border: '1px solid #334155', fontSize: '11px'}} />
                    <Bar dataKey="display" shape={<Candlestick />} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {/* 수급 및 실적 심층 분석 섹션 */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            {/* 수급 현황 (외국인, 기관, 개인) */}
            <div className="bg-[#1a1f2e] p-8 rounded-[2.5rem] border border-slate-700/50 shadow-2xl">
              <div className="flex items-center gap-3 mb-6">
                <Users2 className="w-6 h-6 text-point-cyan" />
                <h3 className="text-sm font-black text-white uppercase tracking-widest">일자별 수급 현황</h3>
              </div>
              <div className="h-56 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={supplyDemandData}>
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
              </div>
            </div>

            {/* 분기별 영업이익률 추이 */}
            <div className="bg-[#1a1f2e] p-8 rounded-[2.5rem] border border-slate-700/50 shadow-2xl">
              <div className="flex items-center gap-3 mb-6">
                <PieChart className="w-6 h-6 text-point-green" />
                <h3 className="text-sm font-black text-white uppercase tracking-widest">영업이익률 추이</h3>
              </div>
              <div className="h-56 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={stock.quarterlyMargins}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#2d3446" />
                    <XAxis dataKey="quarter" axisLine={false} tickLine={false} tick={{fill: '#475569', fontSize: 10}} />
                    <YAxis axisLine={false} tickLine={false} tick={{fill: '#475569', fontSize: 10}} tickFormatter={(v) => `${v}%`} />
                    <Tooltip contentStyle={{backgroundColor: '#0f121d', borderRadius: '12px', border: '1px solid #334155', fontSize: '11px'}} />
                    <Bar dataKey="margin" radius={[6, 6, 0, 0]}>
                      {stock.quarterlyMargins.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.margin >= 0 ? '#22c55e' : '#f43f5e'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
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

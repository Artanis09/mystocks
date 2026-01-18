
import React from 'react';
import { StockData } from '../types';
import { TrendingUp, TrendingDown, Users, Sparkles, X } from 'lucide-react';

interface StockCardProps {
  stock: StockData;
  onClick: (stock: StockData) => void;
  onDelete?: (id: string) => void;
}

// 시가총액을 한국어 단위로 변환 (예: 8조2천2백억)
const formatMarketCap = (value: string | number): string => {
  let num: number;
  if (typeof value === 'string') {
    num = parseFloat(value.replace(/,/g, ''));
  } else {
    num = value;
  }
  
  if (isNaN(num) || num === 0) return '-';
  
  // 억 단위 기준 (KIS API는 억 단위로 반환)
  // 먼저 원 단위인지 억 단위인지 판단
  if (num >= 1000000000000) {
    // 원 단위로 추정 (1조 이상)
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
    // 원 단위 (1억 이상)
    return `${Math.floor(num / 100000000).toLocaleString()}억`;
  } else if (num >= 10000) {
    // 억 단위로 이미 제공된 경우 (10000억 = 1조)
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
    // 억 단위
    return `${Math.floor(num).toLocaleString()}억`;
  }
  
  return '-';
};

export const StockCard: React.FC<StockCardProps> = ({ stock, onClick, onDelete }) => {
  const latestMargin = stock.quarterlyMargins[stock.quarterlyMargins.length - 1]?.margin || 0;
  const isProfitable = latestMargin > 0;
  const changePercent = stock.changePercent || 0;
  const isUp = changePercent >= 0;

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onDelete) {
      onDelete(stock.id);
    }
  };

  return (
    <div 
      onClick={() => onClick(stock)}
      className="card-flat rounded-2xl p-6 hover:border-point-cyan/50 hover:bg-[#232a3e] transition-all cursor-pointer group relative overflow-hidden"
    >
      {/* 삭제 버튼 */}
      {onDelete && (
        <button
          onClick={handleDelete}
          className="absolute top-3 right-3 z-20 p-1.5 rounded-full bg-slate-800/80 text-slate-500 hover:bg-rose-500/20 hover:text-rose-400 transition-all opacity-0 group-hover:opacity-100"
          title="종목 삭제"
        >
          <X className="w-4 h-4" />
        </button>
      )}
      <div className="flex justify-between items-start mb-4 relative z-10">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="font-extrabold text-white truncate group-hover:text-point-cyan transition-colors">{stock.name}</h3>
            {isProfitable && <Sparkles className="w-3 h-3 text-point-yellow animate-pulse" />}
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{stock.symbol}</span>
                <span className="text-lg font-extrabold text-white">{(stock.currentPrice || 0).toLocaleString()}원</span>
            <span className={`text-xs font-bold flex items-center gap-0.5 ${isUp ? 'text-rose-400' : 'text-blue-400'}`}>
              {isUp ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
              {isUp ? '+' : ''}{changePercent.toFixed(2)}%
            </span>
          </div>
        </div>
        <div className="text-right">
              <div className="text-[11px] text-slate-400">{formatMarketCap(stock.marketCap)}</div>
              <div className="text-[9px] text-slate-500 font-bold uppercase">시총</div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 mb-5 relative z-10">
        <div className="bg-[#0f121d] rounded-xl p-2 flex flex-col items-center border border-slate-700/50">
          <span className="text-[9px] text-slate-500 font-black mb-0.5 uppercase">PER</span>
          <span className="text-xs font-black text-point-yellow">{stock.per.toFixed(1)}</span>
        </div>
        <div className="bg-[#0f121d] rounded-xl p-2 flex flex-col items-center border border-slate-700/50">
          <span className="text-[9px] text-slate-500 font-black mb-0.5 uppercase">PBR</span>
          <span className="text-xs font-black text-point-cyan">{stock.pbr.toFixed(1)}</span>
        </div>
        <div className="bg-[#0f121d] rounded-xl p-2 flex flex-col items-center border border-slate-700/50">
          <span className="text-[9px] text-slate-500 font-black mb-0.5 uppercase">EPS</span>
          <span className="text-xs font-black text-point-orange">{stock.eps.toLocaleString()}</span>
        </div>
      </div>

      <div className="flex items-center justify-between pt-4 border-t border-slate-700/50 relative z-10">
        <div className="flex items-center gap-3">
          <div className={`flex items-center gap-1.5 text-[11px] font-black ${isProfitable ? 'text-point-green' : 'text-rose-400'}`}>
            {isProfitable ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
            {latestMargin}%
          </div>
          <div className="flex items-center gap-1 text-[11px] text-slate-400 font-bold">
            <Users className="w-3.5 h-3.5 text-point-cyan" />
            {stock.foreignOwnership}%
          </div>
        </div>
        <div className="flex items-center justify-center bg-slate-700 text-white text-[10px] font-black w-6 h-6 rounded-full">
          {stock.memos.length}
        </div>
      </div>
    </div>
  );
};

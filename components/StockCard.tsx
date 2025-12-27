
import React from 'react';
import { StockData } from '../types';
import { TrendingUp, TrendingDown, Users, Sparkles } from 'lucide-react';

interface StockCardProps {
  stock: StockData;
  onClick: (stock: StockData) => void;
}

export const StockCard: React.FC<StockCardProps> = ({ stock, onClick }) => {
  const latestMargin = stock.quarterlyMargins[stock.quarterlyMargins.length - 1]?.margin || 0;
  const isProfitable = latestMargin > 0;

  return (
    <div 
      onClick={() => onClick(stock)}
      className="card-flat rounded-2xl p-6 hover:border-point-cyan/50 hover:bg-[#232a3e] transition-all cursor-pointer group relative overflow-hidden"
    >
      <div className="flex justify-between items-start mb-4 relative z-10">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="font-extrabold text-white truncate group-hover:text-point-cyan transition-colors">{stock.name}</h3>
            {isProfitable && <Sparkles className="w-3 h-3 text-point-yellow animate-pulse" />}
          </div>
          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{stock.symbol}</span>
        </div>
        <div className="text-right">
          <div className="text-sm font-black text-slate-200">{stock.marketCap}</div>
          <div className="text-[9px] text-slate-500 font-bold uppercase">Market Cap</div>
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

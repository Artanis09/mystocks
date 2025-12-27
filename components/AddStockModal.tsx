
import React, { useState } from 'react';
import { Button } from './Button';
import { fetchStockDataBulk } from '../services/geminiService';
import { StockData } from '../types';
import { X, ListPlus, Tag, Info, Sparkles } from 'lucide-react';

interface AddStockModalProps {
  onClose: () => void;
  onAdd: (groupName: string, stocks: Partial<StockData>[]) => void;
}

export const AddStockModal: React.FC<AddStockModalProps> = ({ onClose, onAdd }) => {
  const [groupName, setGroupName] = useState(`${new Date().toLocaleDateString()} 발굴 종목`);
  const [input, setInput] = useState('');
  const [isSearching, setIsSearching] = useState(false);

  const handleRegister = async () => {
    const names = input.split(/[,|\n]/).map(n => n.trim()).filter(n => n.length > 0);
    if (names.length === 0) return;

    setIsSearching(true);
    try {
      const results = await fetchStockDataBulk(names);
      onAdd(groupName, results);
      onClose();
    } catch (e) {
      console.error(e);
      alert("종목 분석 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.");
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-300">
      <div className="bg-[#1e2336] rounded-[3rem] w-full max-w-xl shadow-[0_30px_60px_-15px_rgba(0,0,0,0.6)] overflow-hidden border border-white/10 animate-in zoom-in-95 duration-300">
        <div className="p-10 border-b border-white/5 flex items-center justify-between bg-white/5 relative overflow-hidden">
          <div className="absolute top-0 right-0 w-32 h-32 vivid-gradient opacity-10 blur-3xl"></div>
          <div className="flex items-center relative z-10">
            <div className="vivid-gradient p-4 rounded-2xl mr-5 shadow-2xl shadow-brand-500/40">
              <ListPlus className="w-7 h-7 text-white" />
            </div>
            <div>
              <h2 className="text-3xl font-black text-white tracking-tighter">새 종목 발굴</h2>
              <p className="text-sm text-slate-400 font-bold flex items-center gap-2">
                <Sparkles className="w-3.5 h-3.5 text-accent" />
                AI 엔진이 종목 지표를 즉시 분석합니다
              </p>
            </div>
          </div>
          <button onClick={onClose} className="p-3 hover:bg-white/10 rounded-full transition-all group relative z-10">
            <X className="w-6 h-6 text-slate-500 group-hover:text-white" />
          </button>
        </div>
        
        <div className="p-10 space-y-10">
          <div className="space-y-4">
            <label className="flex items-center text-xs font-black text-slate-400 tracking-[0.2em] uppercase">
              <Tag className="w-4 h-4 mr-2 text-accent" />
              그룹 테마 및 이름
            </label>
            <input
              type="text"
              className="w-full px-6 py-5 border border-slate-700 rounded-3xl focus:ring-4 focus:ring-brand-500/20 focus:border-brand-500 bg-slate-900 text-white font-black transition-all shadow-inner"
              value={groupName}
              onChange={(e) => setGroupName(e.target.value)}
              placeholder="예: 2024년 2분기 반도체 유망주"
              disabled={isSearching}
            />
          </div>

          <div className="space-y-4">
            <label className="block text-xs font-black text-slate-400 tracking-[0.2em] uppercase">
              분석할 종목들
            </label>
            <textarea
              className="w-full h-48 p-6 border border-slate-700 rounded-3xl focus:ring-4 focus:ring-brand-500/20 focus:border-brand-500 resize-none bg-slate-900 text-white placeholder-slate-600 transition-all font-bold leading-relaxed shadow-inner"
              placeholder="종목명을 쉼표나 엔터로 구분하여 입력하세요 (예: 삼성전자, 테슬라, 엔비디아...)"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={isSearching}
            />
            <div className="flex items-start gap-3 pt-2 bg-brand-500/5 p-4 rounded-2xl border border-brand-500/10">
              <Info className="w-5 h-5 text-accent mt-0.5 shrink-0" />
              <p className="text-[12px] text-slate-400 font-bold leading-relaxed">
                입력하신 종목들의 <span className="text-white">수익성(PER, PBR), 유동성(거래대금), 수급(외인비율)</span> 정보를 AI가 실시간으로 수집하여 정리해드립니다.
              </p>
            </div>
          </div>
        </div>

        <div className="p-10 bg-black/20 border-t border-white/5 flex justify-end gap-4">
          <Button variant="ghost" onClick={onClose} disabled={isSearching} className="px-8">
            닫기
          </Button>
          <Button 
            onClick={handleRegister} 
            isLoading={isSearching} 
            disabled={!input.trim() || !groupName.trim() || isSearching}
            variant="vivid"
            className="px-12 py-4 text-lg shadow-2xl"
          >
            {isSearching ? '지표 분석 중...' : '종목 발굴 시작'}
          </Button>
        </div>
      </div>
    </div>
  );
};

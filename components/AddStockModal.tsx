
import React, { useState, useEffect } from 'react';
import { Button } from './Button';
import { StockData, StockGroup } from '../types';
import { loadStockList, loadETFList, searchStocks, searchETFFromCSV, getStockDetail, StockBasicInfo, isETFName, lookupETFByCode } from '../services/stockService';
import { X, ListPlus, Tag, Info, Sparkles, Search, Check, FolderPlus, ChevronDown } from 'lucide-react';

interface AddStockModalProps {
  onClose: () => void;
  onAdd: (groupName: string, stocks: Partial<StockData>[]) => void;
  existingGroups?: StockGroup[];  // 기존 그룹 목록
  onAddToExisting?: (groupId: string, stocks: Partial<StockData>[]) => void;  // 기존 그룹에 추가
  defaultGroupId?: string | null;  // 기본 선택할 그룹 ID (포트폴리오 카드에서 추가 클릭 시)
}

export const AddStockModal: React.FC<AddStockModalProps> = ({ onClose, onAdd, existingGroups = [], onAddToExisting, defaultGroupId }) => {
  const [groupName, setGroupName] = useState(`${new Date().toLocaleDateString()} 발굴 종목`);
  const [input, setInput] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [isLoadingStocks, setIsLoadingStocks] = useState(true);
  const [addToExisting, setAddToExisting] = useState(!!defaultGroupId);  // defaultGroupId가 있으면 기존 그룹 추가 모드로 시작
  const [selectedGroupId, setSelectedGroupId] = useState<string>(defaultGroupId || '');

  useEffect(() => {
    const loadStocks = async () => {
      try {
        await Promise.all([loadStockList(), loadETFList()]);
        setIsLoadingStocks(false);
      } catch (error) {
        console.error('종목 리스트 로딩 실패:', error);
        setIsLoadingStocks(false);
      }
    };
    loadStocks();
  }, []);

  const handleRegister = async () => {
    if (isLoadingStocks) {
      alert('종목 리스트를 로딩 중입니다. 잠시 기다려주세요.');
      return;
    }

    const names = input.split(/[,|\n]/).map(n => n.trim()).filter(n => n.length > 0);
    if (names.length === 0) return;

    setIsSearching(true);
    try {
      const matchedStocks: Partial<StockData>[] = [];
      for (const name of names) {
        // 종목코드로 직접 입력한 경우 (숫자 6자리)
        const isCode = /^\d{6}$/.test(name);
        
        // ETF 키워드 포함 여부 확인 (대소문자 무시)
        const isETF = isETFName(name);
        
        // ETF 키워드가 있거나 종목코드인 경우 KIS API 우선 조회
        if (isETF || isCode) {
          const code = isCode ? name : null;
          
          if (isCode) {
            // 종목코드로 직접 조회
            const etfInfo = await lookupETFByCode(code);
            if (etfInfo) {
              matchedStocks.push({
                symbol: etfInfo.code,
                name: etfInfo.name,
              });
              console.log(`종목 조회 성공: ${etfInfo.name} (${etfInfo.code})`);
              continue;
            }
          }
          
          // ETF 이름으로 검색 - korea_etf.csv에서 검색
          if (!isCode && isETF) {
            const etfCandidates = searchETFFromCSV(name);
            if (etfCandidates.length > 0) {
              const bestMatch = etfCandidates[0];
              matchedStocks.push({
                symbol: bestMatch.code,
                name: bestMatch.name,
              });
              console.log(`ETF 검색 성공 (CSV): ${bestMatch.name} (${bestMatch.code})`);
              continue;
            } else {
              console.warn(`"${name}" ETF를 찾을 수 없습니다. 정확한 종목코드(6자리)를 입력해주세요.`);
            }
          }
          continue;
        }
        
        // 일반 종목은 CSV에서 검색
        const candidates = searchStocks(name);
        if (candidates.length > 0) {
          const bestMatch = candidates[0];  // 가장 유사한 것
          matchedStocks.push({
            symbol: bestMatch.code,
            name: bestMatch.name,
          });
        } else {
          console.warn(`"${name}"에 대한 일치하는 종목을 찾을 수 없습니다.`);
        }
      }

      if (matchedStocks.length > 0) {
        // 등록된 종목들에 대해 데이터 업데이트
        try {
          const response = await fetch('/update-stocks', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              codes: matchedStocks.map(stock => stock.symbol)
            })
          });
          
          if (!response.ok) {
            console.warn('데이터 업데이트 실패:', response.statusText);
          } else {
            console.log('종목 데이터 업데이트 완료');
          }
        } catch (error) {
          console.warn('데이터 업데이트 중 오류:', error);
        }

        // 한국투자증권 API로 상세 정보 가져오기 (현재 모의, 실제로는 API 호출)
        const detailedStocks = await Promise.all(
          matchedStocks.map(async (stock) => {
            const detail = await getStockDetail(stock.symbol!);
            const bestMatch = searchStocks(stock.name!)[0]; // 다시 검색
            return {
              ...stock,
              currentPrice: detail.currentPrice,
              per: detail.per,
              pbr: detail.pbr,
              eps: detail.eps,
              floatingShares: bestMatch ? bestMatch.listedShares.toString() : '0',
              majorShareholderStake: parseFloat(detail.major_shareholder_stake.replace('%', '')) || 0,
              marketCap: detail.marketCap.toString(),
              tradingVolume: detail.volume.toString(),
              transactionAmount: '0',
              foreignOwnership: detail.foreignOwnership,
              quarterlyMargins: detail.quarterlyMargins,
            } as Partial<StockData>;
          })
        );

        // 기존 그룹에 추가 또는 새 그룹 생성
        if (addToExisting && selectedGroupId && onAddToExisting) {
          onAddToExisting(selectedGroupId, detailedStocks);
        } else {
          onAdd(groupName, detailedStocks);
        }
        onClose();
      } else {
        alert("일치하는 종목을 찾을 수 없습니다.");
      }
    } catch (e) {
      console.error(e);
      alert("종목 등록 중 오류가 발생했습니다.");
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
          {/* 그룹 선택 모드 토글 */}
          {existingGroups.length > 0 && (
            <div className="flex gap-4">
              <button
                onClick={() => { setAddToExisting(false); setSelectedGroupId(''); }}
                className={`flex-1 p-4 rounded-2xl border-2 transition-all font-bold ${
                  !addToExisting 
                    ? 'border-point-cyan bg-point-cyan/10 text-point-cyan' 
                    : 'border-slate-700 text-slate-500 hover:border-slate-600'
                }`}
              >
                <ListPlus className="w-5 h-5 mx-auto mb-2" />
                새 그룹 생성
              </button>
              <button
                onClick={() => setAddToExisting(true)}
                className={`flex-1 p-4 rounded-2xl border-2 transition-all font-bold ${
                  addToExisting 
                    ? 'border-point-cyan bg-point-cyan/10 text-point-cyan' 
                    : 'border-slate-700 text-slate-500 hover:border-slate-600'
                }`}
              >
                <FolderPlus className="w-5 h-5 mx-auto mb-2" />
                기존 그룹에 추가
              </button>
            </div>
          )}

          <div className="space-y-4">
            <label className="flex items-center text-xs font-black text-slate-400 tracking-[0.2em] uppercase">
              <Tag className="w-4 h-4 mr-2 text-accent" />
              {addToExisting ? '추가할 그룹 선택' : '그룹 테마 및 이름'}
            </label>
            {addToExisting ? (
              <select
                className="w-full px-6 py-5 border border-slate-700 rounded-3xl focus:ring-4 focus:ring-brand-500/20 focus:border-brand-500 bg-slate-900 text-white font-black transition-all shadow-inner appearance-none cursor-pointer"
                value={selectedGroupId}
                onChange={(e) => setSelectedGroupId(e.target.value)}
                disabled={isSearching}
              >
                <option value="">그룹을 선택하세요</option>
                {existingGroups.map(group => (
                  <option key={group.id} value={group.id}>
                    {group.name} ({group.stocks.length}종목)
                  </option>
                ))}
              </select>
            ) : (
              <input
                type="text"
                className="w-full px-6 py-5 border border-slate-700 rounded-3xl focus:ring-4 focus:ring-brand-500/20 focus:border-brand-500 bg-slate-900 text-white font-black transition-all shadow-inner"
                value={groupName}
                onChange={(e) => setGroupName(e.target.value)}
                placeholder="예: 2024년 2분기 반도체 유망주"
                disabled={isSearching}
              />
            )}
          </div>

          <div className="space-y-4">
            <label className="block text-xs font-black text-slate-400 tracking-[0.2em] uppercase">
              등록할 종목들
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
                입력하신 종목명과 가장 유사한 종목을 찾아 한국투자증권 API로 <span className="text-white">실시간 지표(PER, PBR, 영업이익률 등)</span>를 자동으로 수집합니다.
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
            disabled={!input.trim() || (addToExisting ? !selectedGroupId : !groupName.trim()) || isSearching || isLoadingStocks}
            variant="vivid"
            className="px-12 py-4 text-lg shadow-2xl"
          >
            {isSearching ? '종목 등록 중...' : isLoadingStocks ? '종목 리스트 로딩 중...' : '종목 등록'}
          </Button>
        </div>
      </div>
    </div>
  );
};

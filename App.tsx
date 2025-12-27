
import React, { useState, useEffect } from 'react';
import { StockGroup, StockData } from './types';
import { StockCard } from './components/StockCard';
import { StockDetail } from './components/StockDetail';
import { AddStockModal } from './components/AddStockModal';
import { Button } from './components/Button';
import { 
  TrendingUp, 
  Search, 
  PlusCircle, 
  Calendar, 
  Trash2,
  Edit3,
  SearchCode
} from 'lucide-react';

const STORAGE_KEY = 'mystock_tracker_v3';

const App: React.FC = () => {
  const [groups, setGroups] = useState<StockGroup[]>([]);
  const [selectedStockId, setSelectedStockId] = useState<string | null>(null);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      try {
        setGroups(JSON.parse(saved));
      } catch (e) {
        console.error("데이터 로딩 실패:", e);
      }
    }
  }, []);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(groups));
  }, [groups]);

  const handleAddGroup = (groupName: string, newStocks: Partial<StockData>[]) => {
    const dateStr = new Date().toISOString();
    const formattedStocks: StockData[] = newStocks.map((s, idx) => ({
      ...s as StockData,
      id: `${s.symbol}-${Date.now()}-${idx}`,
      memos: [],
      addedAt: dateStr,
    }));

    const newGroup: StockGroup = {
      id: Date.now().toString(),
      name: groupName,
      date: dateStr,
      stocks: formattedStocks,
    };

    setGroups(prev => [newGroup, ...prev]);
  };

  const handleUpdateStock = (updatedStock: StockData) => {
    setGroups(prev => prev.map(group => ({
      ...group,
      stocks: group.stocks.map(s => s.id === updatedStock.id ? updatedStock : s)
    })));
  };

  const handleDeleteStock = (id: string) => {
    if (confirm("이 종목 분석을 종료하고 영구히 삭제하시겠습니까?")) {
      setGroups(prev => prev.map(group => ({
        ...group,
        stocks: group.stocks.filter(s => s.id !== id)
      })).filter(group => group.stocks.length > 0)); 
      setSelectedStockId(null);
    }
  };

  const handleDeleteGroup = (groupId: string) => {
    if (confirm("이 그룹에 포함된 모든 분석 종목을 삭제하시겠습니까?")) {
      setGroups(prev => prev.filter(g => g.id !== groupId));
    }
  };

  const handleEditGroupName = (groupId: string) => {
    const group = groups.find(g => g.id === groupId);
    if (!group) return;
    const newName = prompt("그룹명을 변경하시겠습니까?", group.name);
    if (newName && newName.trim()) {
      setGroups(prev => prev.map(g => g.id === groupId ? { ...g, name: newName } : g));
    }
  };

  const allStocks = groups.flatMap(g => g.stocks);
  const selectedStock = allStocks.find(s => s.id === selectedStockId);

  const filteredGroups = groups.map(group => ({
    ...group,
    stocks: group.stocks.filter(s => 
      s.name.toLowerCase().includes(searchTerm.toLowerCase()) || 
      s.symbol.toLowerCase().includes(searchTerm.toLowerCase())
    )
  })).filter(group => group.stocks.length > 0);

  return (
    <div className="min-h-screen flex flex-col bg-[#0f121d] text-slate-200 selection:bg-point-cyan/30">
      {/* Header Navigation */}
      <nav className="sticky top-0 z-40 bg-[#0f121d]/80 backdrop-blur-xl border-b border-slate-800">
        <div className="max-w-7xl mx-auto px-6 h-20 flex justify-between items-center">
          <div className="flex items-center space-x-4 cursor-pointer group" onClick={() => setSelectedStockId(null)}>
            <div className="bg-point-cyan p-2 rounded-xl shadow-lg shadow-point-cyan/20 group-hover:scale-105 transition-all">
              <TrendingUp className="w-6 h-6 text-white" />
            </div>
            <div className="flex flex-col">
              <span className="text-2xl font-black tracking-tighter text-white leading-none">마이스탁</span>
              <span className="text-[9px] font-bold text-slate-500 tracking-[0.2em] uppercase mt-1">My Market Insight</span>
            </div>
          </div>

          {selectedStockId === null && (
            <div className="flex-1 max-w-lg mx-12 hidden md:block">
              <div className="relative">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-600" />
                <input 
                  type="text" 
                  placeholder="분석 중인 종목을 검색하세요..."
                  className="w-full pl-12 pr-6 py-2.5 bg-[#1a1f2e] border border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-point-cyan focus:border-transparent transition-all placeholder-slate-600"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
              </div>
            </div>
          )}

          <div className="flex items-center space-x-4">
            <Button onClick={() => setIsAddModalOpen(true)} variant="primary" size="md" className="hidden sm:flex px-6">
              <PlusCircle className="w-5 h-5 mr-2" /> 신규 종목 발굴
            </Button>
            <Button onClick={() => setIsAddModalOpen(true)} variant="primary" size="md" className="sm:hidden p-3 rounded-xl">
              <PlusCircle className="w-6 h-6" />
            </Button>
          </div>
        </div>
      </nav>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl mx-auto px-6 py-12 w-full">
        {selectedStockId && selectedStock ? (
          <StockDetail 
            stock={selectedStock} 
            onBack={() => setSelectedStockId(null)} 
            onUpdate={handleUpdateStock}
            onDelete={handleDeleteStock}
          />
        ) : (
          <div className="animate-in fade-in duration-700">
            {/* Content List */}
            {groups.length === 0 ? (
              <div className="bg-[#1a1f2e] border border-dashed border-slate-700 rounded-[2rem] py-32 px-10 text-center shadow-xl">
                <div className="max-w-xl mx-auto">
                  <div className="bg-[#0f121d] border border-slate-700 w-24 h-24 rounded-2xl flex items-center justify-center mx-auto mb-10">
                    <SearchCode className="w-12 h-12 text-point-cyan opacity-80" />
                  </div>
                  <h2 className="text-3xl font-black text-white mb-6">첫 번째 분석 그룹을 만들어보세요</h2>
                  <p className="text-slate-500 mb-10 text-lg font-bold leading-relaxed">
                    매일 발견되는 신선한 종목들을 테마별로 묶어 관리하고,<br/>일지에 나만의 관점을 기록하세요.
                  </p>
                  <Button onClick={() => setIsAddModalOpen(true)} variant="primary" size="lg" className="px-12 py-4 shadow-xl">
                    지금 바로 발굴 시작하기
                  </Button>
                </div>
              </div>
            ) : (
              <div className="space-y-16">
                {filteredGroups.map((group) => (
                  <section key={group.id} className="animate-in fade-in slide-in-from-left-4 duration-700">
                    <div className="flex flex-wrap items-center justify-between mb-8 px-2 border-b border-slate-800 pb-6 gap-6">
                      <div className="flex items-center group/title cursor-default">
                        <div className="bg-point-cyan p-3 rounded-xl mr-5 shadow-lg shadow-point-cyan/10">
                          <Calendar className="w-6 h-6 text-white" />
                        </div>
                        <div>
                          <div className="flex items-center gap-3">
                            <h2 className="text-2xl font-black text-white tracking-tighter">{group.name}</h2>
                            <button onClick={() => handleEditGroupName(group.id)} className="text-slate-600 hover:text-point-cyan transition-colors">
                              <Edit3 className="w-5 h-5" />
                            </button>
                          </div>
                          <p className="text-[10px] text-slate-500 font-bold uppercase tracking-[0.2em] mt-1.5 flex items-center gap-2">
                            {new Date(group.date).toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'short' })}
                            <span className="w-1 h-1 bg-point-cyan rounded-full"></span>
                            {group.stocks.length} 종목 분석 중
                          </p>
                        </div>
                      </div>
                      
                      <div className="flex items-center gap-3">
                        <button 
                          onClick={() => handleDeleteGroup(group.id)}
                          className="flex items-center gap-2 bg-[#1a1f2e] border border-slate-700 text-slate-500 hover:text-rose-400 hover:border-rose-400 px-4 py-2 rounded-xl text-xs font-bold transition-all"
                        >
                          <Trash2 className="w-4 h-4" />
                          그룹 삭제
                        </button>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                      {group.stocks.map((stock) => (
                        <StockCard 
                          key={stock.id} 
                          stock={stock} 
                          onClick={(s) => setSelectedStockId(s.id)} 
                        />
                      ))}
                    </div>
                  </section>
                ))}
                
                {filteredGroups.length === 0 && searchTerm && (
                  <div className="py-24 text-center bg-[#1a1f2e] rounded-3xl border border-slate-800">
                    <p className="text-slate-500 font-bold text-xl italic tracking-tight">"{searchTerm}" 종목을 찾을 수 없습니다.</p>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="bg-[#0b0d14] border-t border-slate-800 py-16 mt-32">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex flex-col md:flex-row justify-between items-center gap-10">
            <div>
              <div className="flex items-center space-x-3 mb-4">
                <div className="bg-point-cyan p-2 rounded-lg">
                  <TrendingUp className="w-6 h-6 text-white" />
                </div>
                <span className="text-xl font-black text-white tracking-tighter">마이스탁</span>
              </div>
              <p className="text-slate-500 text-sm font-bold leading-loose">
                성공적인 투자를 위한 나만의 스마트한 기록지.
              </p>
            </div>
            <div className="flex gap-8 text-[11px] font-black text-slate-600 uppercase tracking-widest">
              <a href="#" className="hover:text-point-cyan transition-colors">Privacy</a>
              <a href="#" className="hover:text-point-cyan transition-colors">Terms</a>
              <a href="#" className="hover:text-point-cyan transition-colors">Contact</a>
            </div>
          </div>
          <div className="mt-12 pt-8 border-t border-slate-800 flex justify-between items-center">
            <p className="text-slate-700 text-[10px] font-black uppercase tracking-[0.4em]">
              © {new Date().getFullYear()} MYSTOCK ANALYTICS.
            </p>
          </div>
        </div>
      </footer>

      {isAddModalOpen && (
        <AddStockModal 
          onClose={() => setIsAddModalOpen(false)} 
          onAdd={handleAddGroup} 
        />
      )}
    </div>
  );
};

export default App;

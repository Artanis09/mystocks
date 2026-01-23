
import React, { useState, useEffect } from 'react';
import { StockGroup, StockData, PageType, RecommendedStock } from './types';
import { Sidebar } from './components/Sidebar';
import { MobileNav } from './components/MobileNav';
import { Dashboard } from './components/Dashboard';
import { JournalPage } from './components/JournalPage';
import { Recommendations } from './components/Recommendations';
import { StockCard } from './components/StockCard';
import { StockDetail } from './components/StockDetail';
import { AddStockModal } from './components/AddStockModal';
import { GroupReturnsPanel } from './components/GroupReturnsPanel';
import { Button } from './components/Button';
import { useResponsive } from './hooks/useResponsive';
import { 
  Search, 
  PlusCircle, 
  Calendar, 
  Trash2,
  Edit3,
  SearchCode,
  ChevronDown,
  ChevronUp,
  Plus
} from 'lucide-react';

// Use relative path for API calls to work with domain/proxy
const API_BASE_URL = '/api';

interface GroupReturnSummary {
  totalProfit: number;
  totalProfitPercent: number;
  totalCost: number;
  currentValue: number;
}

const App: React.FC = () => {
  const [currentPage, setCurrentPage] = useState<PageType>('recommendations');
  const [groups, setGroups] = useState<StockGroup[]>([]);
  const [selectedStockId, setSelectedStockId] = useState<string | null>(null);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [addToGroupId, setAddToGroupId] = useState<string | null>(null);  // 특정 그룹에 추가할 때
  const [searchTerm, setSearchTerm] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [expandedGroupId, setExpandedGroupId] = useState<string | null>(null);
  const [groupReturns, setGroupReturns] = useState<{ [key: string]: GroupReturnSummary }>({});
  const [selectedRecStock, setSelectedRecStock] = useState<StockData | null>(null);

  // 반응형 디바이스 정보
  const { isMobile, isTablet } = useResponsive();

  // 그룹별 수익률 로드
  const loadGroupReturns = async (groupIds: string[]) => {
    const returns: { [key: string]: GroupReturnSummary } = {};
    
    await Promise.all(
      groupIds.map(async (groupId) => {
        try {
          const response = await fetch(`${API_BASE_URL}/groups/${groupId}/returns`);
          if (response.ok) {
            const data = await response.json();
            if (data.summary) {
              returns[groupId] = {
                totalProfit: data.summary.totalProfit || 0,
                // 백엔드에서 returnRate로 오는지 totalProfitPercent로 오는지 확인 필요
                totalProfitPercent: data.summary.returnRate !== undefined ? data.summary.returnRate : (data.summary.totalProfitPercent || 0),
                totalCost: data.summary.totalInvested !== undefined ? data.summary.totalInvested : (data.summary.totalCost || 0),
                currentValue: data.summary.totalCurrentValue !== undefined ? data.summary.totalCurrentValue : (data.summary.currentValue || 0),
              };
            }
          }
        } catch (error) {
          console.error(`그룹 ${groupId} 수익률 로딩 실패:`, error);
        }
      })
    );
    
    setGroupReturns(returns);
  };

  // API에서 그룹 데이터 로드
  const loadGroups = async () => {
    try {
      console.log('그룹 데이터 로딩 시작...');
      const response = await fetch(`${API_BASE_URL}/groups`);
      console.log('API 응답 상태:', response.status);
      if (response.ok) {
        const data = await response.json();
        console.log('받은 데이터:', data);
        setGroups(data);
        
        // 그룹별 수익률 로드
        const groupIds = data.map((g: StockGroup) => g.id);
        if (groupIds.length > 0) {
          loadGroupReturns(groupIds);
        }
      } else {
        console.error('그룹 데이터 로딩 실패:', response.status, response.statusText);
      }
    } catch (error) {
      console.error('API 호출 실패:', error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadGroups();
  }, []);

  const handleAddGroup = async (groupName: string, newStocks: Partial<StockData>[]) => {
    try {
      const response = await fetch(`${API_BASE_URL}/groups`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: groupName,
          stocks: newStocks
        })
      });

      if (response.ok) {
        await loadGroups();
      } else {
        console.error('그룹 생성 실패');
        alert('그룹 생성에 실패했습니다.');
      }
    } catch (error) {
      console.error('API 호출 실패:', error);
      alert('서버 연결에 실패했습니다.');
    }
  };

  // 기존 그룹에 종목 추가
  const handleAddToExistingGroup = async (groupId: string, newStocks: Partial<StockData>[]) => {
    try {
      const response = await fetch(`${API_BASE_URL}/groups/${groupId}/stocks`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          stocks: newStocks
        })
      });

      if (response.ok) {
        await loadGroups();
        setAddToGroupId(null);
      } else {
        console.error('종목 추가 실패');
        alert('종목 추가에 실패했습니다.');
      }
    } catch (error) {
      console.error('API 호출 실패:', error);
      alert('서버 연결에 실패했습니다.');
    }
  };

  // 특정 그룹에 종목 추가 모달 열기
  const handleOpenAddToGroup = (groupId: string) => {
    setAddToGroupId(groupId);
    setIsAddModalOpen(true);
  };

  const handleUpdateStock = async (updatedStock: StockData) => {
    try {
      const response = await fetch(`${API_BASE_URL}/stocks/${updatedStock.id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          price: updatedStock.currentPrice,
          change: updatedStock.change,
          changePercent: updatedStock.changePercent,
          per: updatedStock.per,
          pbr: updatedStock.pbr,
          eps: updatedStock.eps,
        })
      });

      if (response.ok) {
        setGroups(prev => prev.map(group => ({
          ...group,
          stocks: group.stocks.map(s => s.id === updatedStock.id ? updatedStock : s)
        })));
      } else {
        console.error('주식 업데이트 실패');
      }
    } catch (error) {
      console.error('API 호출 실패:', error);
    }
  };

  const handleDeleteStock = async (id: string) => {
    if (!confirm("이 종목 분석을 종료하고 영구히 삭제하시겠습니까?")) {
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/stocks/${id}`, {
        method: 'DELETE'
      });

      if (response.ok) {
        setGroups(prev => prev.map(group => ({
          ...group,
          stocks: group.stocks.filter(s => s.id !== id)
        })).filter(group => group.stocks.length > 0));
        setSelectedStockId(null);
      } else {
        console.error('주식 삭제 실패');
        alert('주식 삭제에 실패했습니다.');
      }
    } catch (error) {
      console.error('API 호출 실패:', error);
      alert('서버 연결에 실패했습니다.');
    }
  };

  const handleRecStockClick = (rec: RecommendedStock) => {
    const allStocks = groups.flatMap(g => g.stocks);
    const existing = allStocks.find(s => s.symbol === rec.code);
    
    if (existing) {
      setSelectedStockId(existing.id);
      setCurrentPage('portfolio');
    } else {
      const tempStock: StockData = {
        id: `temp_${rec.code}`,
        symbol: rec.code,
        name: rec.name,
        currentPrice: rec.current_price || rec.close, // 현재가가 있으면 우선 사용
        per: 0,
        pbr: 0,
        eps: 0,
        floatingShares: '0',
        majorShareholderStake: 0,
        marketCap: rec.market_cap.toString(),
        tradingVolume: '0',
        transactionAmount: '0',
        foreignOwnership: 0,
        quarterlyMargins: [],
        memos: [],
        addedAt: new Date().toISOString()
      };
      setSelectedRecStock(tempStock);
    }
  };

  const handleDeleteGroup = async (groupId: string) => {
    if (!confirm("이 그룹에 포함된 모든 분석 종목을 삭제하시겠습니까?")) {
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/groups/${groupId}`, {
        method: 'DELETE'
      });

      if (response.ok) {
        setGroups(prev => prev.filter(g => g.id !== groupId));
      } else {
        console.error('그룹 삭제 실패');
        alert('그룹 삭제에 실패했습니다.');
      }
    } catch (error) {
      console.error('API 호출 실패:', error);
      alert('서버 연결에 실패했습니다.');
    }
  };

  const handleEditGroupName = async (groupId: string) => {
    const group = groups.find(g => g.id === groupId);
    if (!group) return;
    
    const newName = prompt("그룹명을 변경하시겠습니까?", group.name);
    if (!newName || newName.trim() === group.name) return;

    try {
      const response = await fetch(`${API_BASE_URL}/groups/${groupId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ name: newName.trim() })
      });

      if (response.ok) {
        setGroups(prev => prev.map(g => g.id === groupId ? { ...g, name: newName.trim() } : g));
      } else {
        console.error('그룹명 변경 실패');
        alert('그룹명 변경에 실패했습니다.');
      }
    } catch (error) {
      console.error('API 호출 실패:', error);
      alert('서버 연결에 실패했습니다.');
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

  const renderPortfolioPage = () => (
    <div className="animate-in fade-in duration-700">
      {selectedStockId && selectedStock ? (
        <StockDetail 
          stock={selectedStock} 
          onBack={() => setSelectedStockId(null)} 
          onUpdate={handleUpdateStock}
          onDelete={handleDeleteStock}
        />
      ) : (
        <>
          {/* Search and Add */}
          <div className="flex items-center justify-between gap-4 mb-8">
            <div className="relative flex-1 max-w-lg">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-600" />
              <input 
                type="text" 
                placeholder="분석 중인 종목을 검색하세요..."
                className="w-full pl-12 pr-6 py-2.5 bg-[#1a1f2e] border border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-point-cyan focus:border-transparent transition-all placeholder-slate-600"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>
            <Button onClick={() => setIsAddModalOpen(true)} variant="primary" size="md" className="px-6">
              <PlusCircle className="w-5 h-5 mr-2" /> 신규 종목 발굴
            </Button>
          </div>

          {/* Content */}
          {isLoading ? (
            <div className="bg-[#1a1f2e] border border-dashed border-slate-700 rounded-[2rem] py-32 px-10 text-center shadow-xl">
              <div className="max-w-xl mx-auto">
                <div className="bg-[#0f121d] border border-slate-700 w-24 h-24 rounded-2xl flex items-center justify-center mx-auto mb-10 animate-pulse">
                  <SearchCode className="w-12 h-12 text-point-cyan opacity-80" />
                </div>
                <h2 className="text-3xl font-black text-white mb-6">데이터를 불러오는 중...</h2>
              </div>
            </div>
          ) : groups.length === 0 ? (
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
            <div className="space-y-6">
              {filteredGroups.map((group) => {
                const returns = groupReturns[group.id];
                const hasReturns = returns && (returns.totalCost > 0 || returns.totalProfit !== 0);
                
                return (
                <section key={group.id} className="bg-[#1a1f2e] border border-slate-800 rounded-2xl overflow-hidden">
                  {/* Group Header */}
                  <div className="flex flex-wrap items-center justify-between p-5 border-b border-slate-800 gap-4">
                    <div className="flex items-center group/title cursor-default">
                      <div className="bg-point-cyan p-3 rounded-xl mr-4 shadow-lg shadow-point-cyan/10">
                        <Calendar className="w-5 h-5 text-white" />
                      </div>
                      <div>
                        <div className="flex items-center gap-3">
                          <h2 className="text-xl font-black text-white tracking-tighter">{group.name}</h2>
                          {/* 포트폴리오 수익률 표시 */}
                          {hasReturns && (
                            <span className={`px-3 py-1 rounded-full text-sm font-bold ${
                              (returns.totalProfitPercent || (returns as any).returnRate || 0) >= 0 
                                ? 'bg-green-500/20 text-green-400' 
                                : 'bg-red-500/20 text-red-400'
                            }`}>
                              {(returns.totalProfitPercent || (returns as any).returnRate || 0) >= 0 ? '+' : ''}{(returns.totalProfitPercent || (returns as any).returnRate || 0).toFixed(2)}%
                            </span>
                          )}
                          <button onClick={() => handleEditGroupName(group.id)} className="text-slate-600 hover:text-point-cyan transition-colors">
                            <Edit3 className="w-4 h-4" />
                          </button>
                        </div>
                        <p className="text-[10px] text-slate-500 font-bold uppercase tracking-[0.2em] mt-1 flex items-center gap-2">
                          {new Date(group.date).toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric' })}
                          <span className="w-1 h-1 bg-point-cyan rounded-full"></span>
                          {group.stocks.length} 종목
                        </p>
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-3">
                      <button 
                        onClick={() => handleOpenAddToGroup(group.id)}
                        className="flex items-center gap-2 bg-point-green/10 border border-point-green/30 text-point-green hover:bg-point-green/20 px-4 py-2 rounded-xl text-xs font-bold transition-all"
                        title="이 그룹에 종목 추가"
                      >
                        <Plus className="w-4 h-4" />
                        종목추가
                      </button>
                      <button 
                        onClick={() => setExpandedGroupId(expandedGroupId === group.id ? null : group.id)}
                        className="flex items-center gap-2 bg-point-cyan/10 border border-point-cyan/30 text-point-cyan hover:bg-point-cyan/20 px-4 py-2 rounded-xl text-xs font-bold transition-all"
                      >
                        {expandedGroupId === group.id ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                        수익률
                      </button>
                      <button 
                        onClick={() => handleDeleteGroup(group.id)}
                        className="flex items-center gap-2 bg-[#0f121d] border border-slate-700 text-slate-500 hover:text-rose-400 hover:border-rose-400 px-4 py-2 rounded-xl text-xs font-bold transition-all"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>

                  {/* Accordion Returns Panel */}
                  {expandedGroupId === group.id && (
                    <div className="border-b border-slate-800">
                      <GroupReturnsPanel groupId={group.id} groupName={group.name} />
                    </div>
                  )}

                  {/* Stock Cards */}
                  <div className="p-5">
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                      {group.stocks.map((stock) => (
                        <StockCard 
                          key={stock.id} 
                          stock={stock} 
                          onClick={(s) => setSelectedStockId(s.id)}
                          onDelete={handleDeleteStock}
                        />
                      ))}
                    </div>
                  </div>
                </section>
              );
              })}
              
              {filteredGroups.length === 0 && searchTerm && (
                <div className="py-24 text-center bg-[#1a1f2e] rounded-3xl border border-slate-800">
                  <p className="text-slate-500 font-bold text-xl italic tracking-tight">"{searchTerm}" 종목을 찾을 수 없습니다.</p>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );

  const renderMainContent = () => {
    switch (currentPage) {
      case 'dashboard':
        return <Dashboard />;
      case 'portfolio':
        return renderPortfolioPage();
      case 'journal':
        return <JournalPage />;
      case 'recommendations':
        if (selectedRecStock) {
          return (
            <div className="animate-in fade-in duration-700">
              <StockDetail 
                stock={selectedRecStock} 
                onBack={() => setSelectedRecStock(null)} 
                onUpdate={() => {}} 
                onDelete={() => setSelectedRecStock(null)}
              />
            </div>
          );
        }
        return <Recommendations onStockClick={handleRecStockClick} />;
      default:
        return <Dashboard />;
    }
  };

  return (
    <div className="min-h-screen flex flex-col md:flex-row bg-[#0f121d] text-slate-200 selection:bg-point-cyan/30">
      {/* 모바일 네비게이션 */}
      {isMobile && (
        <MobileNav 
          currentPage={currentPage} 
          onPageChange={(page) => {
            setCurrentPage(page);
            setSelectedStockId(null);
            setSelectedRecStock(null);
          }} 
        />
      )}

      {/* 데스크톱/태블릿 사이드바 */}
      {!isMobile && (
        <Sidebar 
          currentPage={currentPage} 
          onPageChange={(page) => {
            setCurrentPage(page);
            setSelectedStockId(null);
            setSelectedRecStock(null);
          }} 
        />
      )}

      {/* Main Content */}
      <main className={`flex-1 overflow-auto ${isMobile ? 'pt-16 pb-4 px-3' : 'p-8'}`}>
        <div className={`mx-auto ${isMobile ? 'max-w-full' : 'max-w-7xl'}`}>
          {renderMainContent()}
        </div>
      </main>

      {/* Modals */}
      {isAddModalOpen && (
        <AddStockModal 
          onClose={() => { setIsAddModalOpen(false); setAddToGroupId(null); }} 
          onAdd={handleAddGroup}
          existingGroups={groups}
          onAddToExisting={handleAddToExistingGroup}
          defaultGroupId={addToGroupId}
        />
      )}
    </div>
  );
};

export default App;

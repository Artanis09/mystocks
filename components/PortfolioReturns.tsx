import React, { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, RefreshCw, DollarSign, Percent, AlertCircle, Edit2, Check, X, LineChart as LineChartIcon } from 'lucide-react';
import { 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  Tooltip, 
  ResponsiveContainer,
  CartesianGrid
} from 'recharts';

const API_BASE_URL = 'http://localhost:5000/api';

interface HistoryPoint {
  date: string;
  returnRate: number;
  totalValue: number;
  totalInvested: number;
}

interface StockReturn {
  id: string;
  symbol: string;
  name: string;
  purchasePrice: number;
  currentPrice: number;
  returnPercent: number;
  returnAmount: number;
}

interface GroupReturns {
  success: boolean;
  groupId: string;
  groupName: string;
  totalPurchase: number;
  totalCurrent: number;
  totalReturnPercent: number;
  stocks: StockReturn[];
}

interface PortfolioReturnsProps {
  groupId: string;
  groupName: string;
  onClose: () => void;
}

export const PortfolioReturns: React.FC<PortfolioReturnsProps> = ({ groupId, groupName, onClose }) => {
  const [data, setData] = useState<GroupReturns | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editPrice, setEditPrice] = useState<string>('');

  const fetchReturns = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/groups/${groupId}/returns`);
      const result = await response.json();
      if (result.success !== false) { // Result shape might vary
        setData(result);
      } else {
        setError(result.error || '조회안됨');
      }
    } catch (e) {
      setError('서버 연결 실패');
    } finally {
      setLoading(false);
    }
  };

  const fetchHistory = async () => {
    setHistoryLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/groups/${groupId}/returns/history`);
      const result = await response.json();
      if (result.history) {
        setHistory(result.history);
      }
    } catch (e) {
      console.error('히스토리 로딩 실패:', e);
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    fetchReturns();
    fetchHistory();
  }, [groupId]);

  const handleEditPurchasePrice = (stockId: string, currentPrice: number) => {
    setEditingId(stockId);
    setEditPrice(currentPrice.toString());
  };

  const handleSavePurchasePrice = async (stockId: string) => {
    try {
      const response = await fetch(`${API_BASE_URL}/stocks/${stockId}/purchase-price`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ purchasePrice: parseFloat(editPrice) || 0 })
      });
      if (response.ok) {
        setEditingId(null);
        fetchReturns(); // 수익률 재계산
      }
    } catch (e) {
      console.error('매입가 저장 실패:', e);
    }
  };

  const formatNumber = (num: number) => {
    if (num >= 100000000) {
      return `${(num / 100000000).toFixed(1)}억`;
    } else if (num >= 10000) {
      return `${(num / 10000).toFixed(0)}만`;
    }
    return num.toLocaleString();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-300">
      <div className="bg-[#1e2336] rounded-[2rem] w-full max-w-4xl max-h-[90vh] overflow-hidden border border-white/10 shadow-2xl">
        {/* 헤더 */}
        <div className="p-8 border-b border-white/10 bg-white/5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="p-3 bg-point-cyan/10 rounded-xl border border-point-cyan/20">
                <DollarSign className="w-7 h-7 text-point-cyan" />
              </div>
              <div>
                <h2 className="text-2xl font-black text-white tracking-tight">{groupName}</h2>
                <p className="text-sm text-slate-400 font-bold">포트폴리오 수익률 모니터링</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={fetchReturns}
                className="p-2 hover:bg-white/10 rounded-xl transition-colors"
                title="새로고침"
              >
                <RefreshCw className={`w-5 h-5 text-slate-400 ${loading ? 'animate-spin' : ''}`} />
              </button>
              <button
                onClick={onClose}
                className="p-2 hover:bg-white/10 rounded-xl transition-colors"
              >
                <X className="w-6 h-6 text-slate-400" />
              </button>
            </div>
          </div>
        </div>

        {/* 컨텐츠 */}
        <div className="p-8 overflow-y-auto max-h-[calc(90vh-200px)]">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <p className="text-slate-500 font-bold">로딩 중...</p>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center py-16 text-slate-500">
              <AlertCircle className="w-12 h-12 mb-4 text-slate-600" />
              <p className="text-lg font-bold">{error}</p>
            </div>
          ) : data ? (
            <>
              {/* 전체 수익률 요약 */}
              <div className="mb-8 p-6 bg-[#0f121d] rounded-2xl border border-slate-700">
                <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                  <div>
                    <p className="text-[10px] text-slate-500 font-black uppercase mb-1">총 매입가</p>
                    <p className="text-xl font-black text-white">{formatNumber(data.totalPurchase || (data as any).summary?.totalInvested || 0)}원</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-500 font-black uppercase mb-1">현재 평가액</p>
                    <p className="text-xl font-black text-white">{formatNumber(data.totalCurrent || (data as any).summary?.totalCurrentValue || 0)}원</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-500 font-black uppercase mb-1">손익금액</p>
                    <p className={`text-xl font-black ${(data.totalCurrent || (data as any).summary?.totalCurrentValue || 0) - (data.totalPurchase || (data as any).summary?.totalInvested || 0) >= 0 ? 'text-point-green' : 'text-rose-400'}`}>
                      {(data.totalCurrent || (data as any).summary?.totalCurrentValue || 0) - (data.totalPurchase || (data as any).summary?.totalInvested || 0) >= 0 ? '+' : ''}
                      {formatNumber((data.totalCurrent || (data as any).summary?.totalCurrentValue || 0) - (data.totalPurchase || (data as any).summary?.totalInvested || 0))}원
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className={`p-3 rounded-xl ${(data.totalReturnPercent || (data as any).summary?.returnRate || 0) >= 0 ? 'bg-point-green/10' : 'bg-rose-400/10'}`}>
                      {(data.totalReturnPercent || (data as any).summary?.returnRate || 0) >= 0 ? (
                        <TrendingUp className="w-6 h-6 text-point-green" />
                      ) : (
                        <TrendingDown className="w-6 h-6 text-rose-400" />
                      )}
                    </div>
                    <div>
                      <p className="text-[10px] text-slate-500 font-black uppercase mb-1">총 수익률</p>
                      <p className={`text-2xl font-black ${(data.totalReturnPercent || (data as any).summary?.returnRate || 0) >= 0 ? 'text-point-green' : 'text-rose-400'}`}>
                        {(data.totalReturnPercent || (data as any).summary?.returnRate || 0) >= 0 ? '+' : ''}
                        {(data.totalReturnPercent || (data as any).summary?.returnRate || 0).toFixed(2)}%
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              {/* 수익률 추이 그래프 */}
              <div className="mb-8 p-6 bg-[#0f121d] rounded-2xl border border-slate-700">
                <div className="flex items-center justify-between mb-6">
                  <div className="flex items-center gap-2">
                    <LineChartIcon className="w-5 h-5 text-point-cyan" />
                    <h3 className="text-lg font-black text-white uppercase tracking-wider">수익률 추이</h3>
                  </div>
                  {historyLoading && <RefreshCw className="w-4 h-4 text-slate-500 animate-spin" />}
                </div>
                <div className="h-64 w-full">
                  {history.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={history}>
                        <defs>
                          <linearGradient id="colorReturn" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#00f2ff" stopOpacity={0.3}/>
                            <stop offset="95%" stopColor="#00f2ff" stopOpacity={0}/>
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#1e2336" vertical={false} />
                        <XAxis 
                          dataKey="date" 
                          stroke="#475569" 
                          fontSize={10} 
                          tickFormatter={(str) => str.split('-').slice(1).join('/')}
                        />
                        <YAxis 
                          stroke="#475569" 
                          fontSize={10} 
                          tickFormatter={(val) => `${val}%`}
                        />
                        <Tooltip 
                          contentStyle={{ backgroundColor: '#1a1f2e', border: '1px solid #334155', borderRadius: '8px' }}
                          labelStyle={{ color: '#94a3b8', fontWeight: 'bold' }}
                          itemStyle={{ fontWeight: 'bold' }}
                        />
                        <Area 
                          type="monotone" 
                          dataKey="returnRate" 
                          name="수익률"
                          stroke="#00f2ff" 
                          strokeWidth={3}
                          fillOpacity={1} 
                          fill="url(#colorReturn)" 
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="flex items-center justify-center h-full text-slate-500 font-bold">
                      {historyLoading ? "데이터 계산 중..." : "매매 히스토리가 부족합니다."}
                    </div>
                  )}
                </div>
              </div>

              {/* 종목별 수익률 */}
              <div className="space-y-3">
                <h3 className="text-sm font-black text-slate-400 uppercase tracking-widest mb-4">종목별 상세</h3>
                {data.stocks.map((stock) => (
                  <div
                    key={stock.id}
                    className="p-5 bg-[#0f121d] rounded-xl border border-slate-700 hover:border-slate-600 transition-colors"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <div className={`p-2 rounded-lg ${stock.returnPercent >= 0 ? 'bg-point-green/10' : 'bg-rose-400/10'}`}>
                          {stock.returnPercent >= 0 ? (
                            <TrendingUp className="w-4 h-4 text-point-green" />
                          ) : (
                            <TrendingDown className="w-4 h-4 text-rose-400" />
                          )}
                        </div>
                        <div>
                          <p className="font-black text-white">{stock.name}</p>
                          <p className="text-[10px] text-slate-500 font-bold">{stock.symbol}</p>
                        </div>
                      </div>

                      <div className="flex items-center gap-6 text-sm">
                        <div className="text-right">
                          <p className="text-[10px] text-slate-500 font-black uppercase">매입가</p>
                          {editingId === stock.id ? (
                            <div className="flex items-center gap-2">
                              <input
                                type="number"
                                value={editPrice}
                                onChange={(e) => setEditPrice(e.target.value)}
                                className="w-24 px-2 py-1 text-right bg-slate-800 border border-slate-600 rounded text-white text-sm"
                                autoFocus
                              />
                              <button onClick={() => handleSavePurchasePrice(stock.id)} className="text-point-green">
                                <Check className="w-4 h-4" />
                              </button>
                              <button onClick={() => setEditingId(null)} className="text-rose-400">
                                <X className="w-4 h-4" />
                              </button>
                            </div>
                          ) : (
                            <div className="flex items-center gap-2">
                              <p className="font-bold text-white">{formatNumber(stock.purchasePrice)}원</p>
                              <button
                                onClick={() => handleEditPurchasePrice(stock.id, stock.purchasePrice)}
                                className="text-slate-500 hover:text-point-cyan transition-colors"
                              >
                                <Edit2 className="w-3 h-3" />
                              </button>
                            </div>
                          )}
                        </div>
                        <div className="text-right">
                          <p className="text-[10px] text-slate-500 font-black uppercase">현재가</p>
                          <p className="font-bold text-white">{formatNumber(stock.currentPrice)}원</p>
                        </div>
                        <div className="text-right min-w-[80px]">
                          <p className="text-[10px] text-slate-500 font-black uppercase">수익률</p>
                          <p className={`font-black ${stock.returnPercent >= 0 ? 'text-point-green' : 'text-rose-400'}`}>
                            {stock.returnPercent >= 0 ? '+' : ''}{stock.returnPercent.toFixed(2)}%
                          </p>
                        </div>
                        <div className="text-right min-w-[100px]">
                          <p className="text-[10px] text-slate-500 font-black uppercase">손익금액</p>
                          <p className={`font-bold ${stock.returnAmount >= 0 ? 'text-point-green' : 'text-rose-400'}`}>
                            {stock.returnAmount >= 0 ? '+' : ''}{formatNumber(stock.returnAmount)}원
                          </p>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              <p className="text-[11px] text-slate-600 mt-6 text-center font-bold">
                💡 매입가를 수정하려면 각 종목의 매입가 옆 편집 버튼을 클릭하세요
              </p>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
};

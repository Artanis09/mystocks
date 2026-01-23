import React, { useState, useEffect } from 'react';
import { 
  Plus, 
  Trash2, 
  TrendingUp, 
  TrendingDown,
  Calendar,
  Edit3,
  X,
  Save
} from 'lucide-react';
import { Trade, StockReturns } from '../types';
import { Button } from './Button';

const API_BASE_URL = '/api';

interface TradeManagerProps {
  stockId: string;
  stockSymbol: string;
  stockName: string;
  initialOpen?: boolean;
  onFormClose?: () => void;
}

export const TradeManager: React.FC<TradeManagerProps> = ({ stockId, stockSymbol, stockName, initialOpen = false, onFormClose }) => {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [returns, setReturns] = useState<StockReturns | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isFormOpen, setIsFormOpen] = useState(initialOpen);
  const [editingTrade, setEditingTrade] = useState<Trade | null>(null);

  // initialOpen이 변경되면 폼 열기
  useEffect(() => {
    if (initialOpen) {
      setIsFormOpen(true);
    }
  }, [initialOpen]);

  // Form states
  const [tradeType, setTradeType] = useState<'buy' | 'sell'>('buy');
  const [quantity, setQuantity] = useState('');
  const [price, setPrice] = useState('');
  const [tradeDate, setTradeDate] = useState(new Date().toISOString().split('T')[0]);
  const [memo, setMemo] = useState('');

  const loadData = async () => {
    setIsLoading(true);
    try {
      const [tradesRes, returnsRes] = await Promise.all([
        fetch(`${API_BASE_URL}/stocks/${stockId}/trades`),
        fetch(`${API_BASE_URL}/stocks/${stockId}/returns`)
      ]);

      if (tradesRes.ok) {
        const tradesData = await tradesRes.json();
        setTrades(tradesData);
      }

      if (returnsRes.ok) {
        const returnsData = await returnsRes.json();
        setReturns(returnsData);
      }
    } catch (error) {
      console.error('매매 데이터 로딩 실패:', error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [stockId]);

  const resetForm = () => {
    setTradeType('buy');
    setQuantity('');
    setPrice('');
    setTradeDate(new Date().toISOString().split('T')[0]);
    setMemo('');
    setEditingTrade(null);
  };

  const openForm = (trade?: Trade) => {
    if (trade) {
      setEditingTrade(trade);
      setTradeType(trade.tradeType);
      setQuantity(trade.quantity.toString());
      setPrice(trade.price.toString());
      setTradeDate(trade.tradeDate);
      setMemo(trade.memo || '');
    } else {
      resetForm();
    }
    setIsFormOpen(true);
  };

  const closeForm = () => {
    setIsFormOpen(false);
    resetForm();
    if (onFormClose) {
      onFormClose();
    }
  };

  const handleSave = async () => {
    if (!quantity || !price) {
      alert('수량과 가격을 입력해주세요.');
      return;
    }

    try {
      const body = {
        tradeType,
        quantity: parseInt(quantity),
        price: parseFloat(price),
        tradeDate,
        memo
      };

      let response;
      if (editingTrade) {
        response = await fetch(`${API_BASE_URL}/trades/${editingTrade.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        });
      } else {
        response = await fetch(`${API_BASE_URL}/stocks/${stockId}/trades`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        });
      }

      if (response.ok) {
        await loadData();
        closeForm();
      }
    } catch (error) {
      console.error('저장 실패:', error);
      alert('저장에 실패했습니다.');
    }
  };

  const handleDelete = async (tradeId: string) => {
    if (!confirm('이 매매 내역을 삭제하시겠습니까?')) return;

    try {
      const response = await fetch(`${API_BASE_URL}/trades/${tradeId}`, {
        method: 'DELETE'
      });
      if (response.ok) {
        await loadData();
      }
    } catch (error) {
      console.error('삭제 실패:', error);
    }
  };

  const formatNumber = (num: number) => {
    return new Intl.NumberFormat('ko-KR').format(Math.round(num));
  };

  const formatPercent = (num: number) => {
    const sign = num >= 0 ? '+' : '';
    return `${sign}${num.toFixed(2)}%`;
  };

  return (
    <div className="bg-[#1a1f2e] p-6 rounded-2xl border border-slate-700/50 shadow-xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-violet-500/10 rounded-xl border border-violet-500/20">
            <TrendingUp className="w-5 h-5 text-violet-400" />
          </div>
          <div>
            <h3 className="text-sm font-black text-white uppercase tracking-widest">매수/매도 관리</h3>
            <p className="text-[10px] text-slate-500 font-bold">수익률 추적 및 거래 내역</p>
          </div>
        </div>
        <Button onClick={() => openForm()} variant="primary" size="sm">
          <Plus className="w-4 h-4 mr-1" /> 거래 추가
        </Button>
      </div>

      {/* Returns Summary */}
      {returns && returns.totalBuyQuantity > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          <div className="bg-[#0f121d] rounded-xl p-3 border border-slate-800">
            <div className="text-[9px] text-slate-500 uppercase tracking-wider mb-1">보유수량</div>
            <div className="text-lg font-black text-white">{formatNumber(returns.remainingQuantity)}주</div>
          </div>
          <div className="bg-[#0f121d] rounded-xl p-3 border border-slate-800">
            <div className="text-[9px] text-slate-500 uppercase tracking-wider mb-1">평균단가</div>
            <div className="text-lg font-black text-white">{formatNumber(returns.avgBuyPrice)}원</div>
          </div>
          <div className="bg-[#0f121d] rounded-xl p-3 border border-slate-800">
            <div className="text-[9px] text-slate-500 uppercase tracking-wider mb-1">평가손익</div>
            <div className={`text-lg font-black ${returns.unrealizedProfit >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {returns.unrealizedProfit >= 0 ? '+' : ''}{formatNumber(returns.unrealizedProfit)}원
            </div>
          </div>
          <div className={`rounded-xl p-3 border ${returns.returnRate >= 0 ? 'bg-emerald-500/10 border-emerald-500/30' : 'bg-rose-500/10 border-rose-500/30'}`}>
            <div className="text-[9px] text-slate-500 uppercase tracking-wider mb-1">수익률</div>
            <div className={`text-lg font-black ${returns.returnRate >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {formatPercent(returns.returnRate)}
            </div>
          </div>
        </div>
      )}

      {/* Trades List */}
      {isLoading ? (
        <div className="text-center py-8 text-slate-500">로딩 중...</div>
      ) : trades.length === 0 ? (
        <div className="text-center py-8 text-slate-500">
          <p className="font-bold">등록된 매매 내역이 없습니다.</p>
          <p className="text-sm mt-1">거래 추가 버튼을 눌러 매수/매도를 기록하세요.</p>
        </div>
      ) : (
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {trades.map((trade) => (
            <div 
              key={trade.id}
              className="flex items-center justify-between p-3 bg-[#0f121d] rounded-xl border border-slate-800 group hover:border-slate-700 transition-colors"
            >
              <div className="flex items-center gap-3">
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                  trade.tradeType === 'buy' ? 'bg-rose-500/10' : 'bg-emerald-500/10'
                }`}>
                  {trade.tradeType === 'buy' ? (
                    <TrendingDown className="w-4 h-4 text-rose-400" />
                  ) : (
                    <TrendingUp className="w-4 h-4 text-emerald-400" />
                  )}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className={`text-xs font-bold ${trade.tradeType === 'buy' ? 'text-rose-400' : 'text-emerald-400'}`}>
                      {trade.tradeType === 'buy' ? '매수' : '매도'}
                    </span>
                    <span className="text-sm font-bold text-white">{formatNumber(trade.quantity)}주</span>
                    <span className="text-xs text-slate-500">@ {formatNumber(trade.price)}원</span>
                  </div>
                  <div className="flex items-center gap-2 text-[10px] text-slate-500">
                    <Calendar className="w-3 h-3" />
                    <span>{trade.tradeDate}</span>
                    {trade.memo && <span className="text-slate-600">· {trade.memo}</span>}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                <button
                  onClick={() => openForm(trade)}
                  className="p-1.5 text-slate-500 hover:text-point-cyan transition-colors"
                >
                  <Edit3 className="w-4 h-4" />
                </button>
                <button
                  onClick={() => handleDelete(trade.id)}
                  className="p-1.5 text-slate-500 hover:text-rose-400 transition-colors"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Form Modal */}
      {isFormOpen && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#1a1f2e] border border-slate-700 rounded-2xl w-full max-w-md overflow-hidden">
            <div className="flex items-center justify-between p-4 border-b border-slate-800">
              <h3 className="text-lg font-bold text-white">
                {editingTrade ? '거래 수정' : '거래 추가'}
              </h3>
              <button onClick={closeForm} className="text-slate-500 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-4 space-y-4">
              {/* Trade Type */}
              <div>
                <label className="block text-sm font-bold text-slate-400 mb-2">거래 유형</label>
                <div className="flex gap-2">
                  <button
                    onClick={() => setTradeType('buy')}
                    className={`flex-1 py-2 rounded-xl text-sm font-bold transition-all ${
                      tradeType === 'buy' 
                        ? 'bg-rose-500 text-white' 
                        : 'bg-[#0f121d] border border-slate-700 text-slate-400'
                    }`}
                  >
                    매수
                  </button>
                  <button
                    onClick={() => setTradeType('sell')}
                    className={`flex-1 py-2 rounded-xl text-sm font-bold transition-all ${
                      tradeType === 'sell' 
                        ? 'bg-emerald-500 text-white' 
                        : 'bg-[#0f121d] border border-slate-700 text-slate-400'
                    }`}
                  >
                    매도
                  </button>
                </div>
              </div>

              {/* Quantity */}
              <div>
                <label className="block text-sm font-bold text-slate-400 mb-2">수량</label>
                <input
                  type="number"
                  value={quantity}
                  onChange={(e) => setQuantity(e.target.value)}
                  placeholder="0"
                  className="w-full px-4 py-2.5 bg-[#0f121d] border border-slate-700 rounded-xl text-white font-bold focus:ring-2 focus:ring-point-cyan focus:border-transparent"
                />
              </div>

              {/* Price */}
              <div>
                <label className="block text-sm font-bold text-slate-400 mb-2">가격 (원)</label>
                <input
                  type="number"
                  value={price}
                  onChange={(e) => setPrice(e.target.value)}
                  placeholder="0"
                  className="w-full px-4 py-2.5 bg-[#0f121d] border border-slate-700 rounded-xl text-white font-bold focus:ring-2 focus:ring-point-cyan focus:border-transparent"
                />
              </div>

              {/* Date */}
              <div>
                <label className="block text-sm font-bold text-slate-400 mb-2">거래일</label>
                <input
                  type="date"
                  value={tradeDate}
                  onChange={(e) => setTradeDate(e.target.value)}
                  className="w-full px-4 py-2.5 bg-[#0f121d] border border-slate-700 rounded-xl text-white font-bold focus:ring-2 focus:ring-point-cyan focus:border-transparent"
                />
              </div>

              {/* Memo */}
              <div>
                <label className="block text-sm font-bold text-slate-400 mb-2">메모 (선택)</label>
                <input
                  type="text"
                  value={memo}
                  onChange={(e) => setMemo(e.target.value)}
                  placeholder="거래 사유 등..."
                  className="w-full px-4 py-2.5 bg-[#0f121d] border border-slate-700 rounded-xl text-white focus:ring-2 focus:ring-point-cyan focus:border-transparent"
                />
              </div>

              {/* Total */}
              {quantity && price && (
                <div className="bg-[#0f121d] rounded-xl p-4 border border-slate-800">
                  <div className="text-sm text-slate-400 mb-1">총 거래금액</div>
                  <div className="text-xl font-black text-white">
                    {formatNumber(parseInt(quantity) * parseFloat(price))}원
                  </div>
                </div>
              )}
            </div>

            <div className="flex justify-end gap-3 p-4 border-t border-slate-800">
              <Button onClick={closeForm} variant="ghost" size="md">
                취소
              </Button>
              <Button onClick={handleSave} variant="primary" size="md">
                <Save className="w-4 h-4 mr-1" /> 저장
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

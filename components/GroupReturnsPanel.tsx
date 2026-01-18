import React, { useState, useEffect } from 'react';
import { 
  TrendingUp, 
  TrendingDown,
  RefreshCw,
  Plus,
  Minus,
  LineChart as LineChartIcon
} from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Area, ComposedChart } from 'recharts';
import { GroupReturns, StockReturns } from '../types';

const API_BASE_URL = 'http://localhost:5000/api';

interface HistoryData {
  date: string;
  returnRate: number;
  totalValue: number;
  totalInvested: number;
}

interface GroupReturnsPanelProps {
  groupId: string;
  groupName: string;
}

export const GroupReturnsPanel: React.FC<GroupReturnsPanelProps> = ({ groupId, groupName }) => {
  const [returns, setReturns] = useState<GroupReturns | null>(null);
  const [history, setHistory] = useState<HistoryData[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);

  const loadReturns = async () => {
    setIsLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/groups/${groupId}/returns`);
      if (response.ok) {
        const data = await response.json();
        setReturns(data);
      }
    } catch (error) {
      console.error('수익률 로딩 실패:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const loadHistory = async () => {
    setIsLoadingHistory(true);
    try {
      const response = await fetch(`${API_BASE_URL}/groups/${groupId}/returns/history`);
      if (response.ok) {
        const data = await response.json();
        setHistory(data.history || []);
      }
    } catch (error) {
      console.error('수익률 히스토리 로딩 실패:', error);
    } finally {
      setIsLoadingHistory(false);
    }
  };

  useEffect(() => {
    loadReturns();
    loadHistory();
  }, [groupId]);

  const formatNumber = (num: number) => {
    return new Intl.NumberFormat('ko-KR').format(Math.round(num));
  };

  const formatPercent = (num: number) => {
    const sign = num >= 0 ? '+' : '';
    return `${sign}${num.toFixed(2)}%`;
  };

  if (isLoading) {
    return (
      <div className="p-6 flex items-center justify-center">
        <RefreshCw className="w-5 h-5 animate-spin text-slate-500" />
        <span className="ml-2 text-slate-500 font-bold">수익률 계산 중...</span>
      </div>
    );
  }

  if (!returns || !returns.summary || returns.stocks.length === 0) {
    return (
      <div className="p-6 text-center">
        <p className="text-slate-500 font-bold">매매 내역이 없습니다.</p>
        <p className="text-sm text-slate-600 mt-1">각 종목에서 매수/매도를 등록해주세요.</p>
      </div>
    );
  }

  const { summary } = returns;
  const isProfit = (summary?.totalProfit || 0) >= 0;

  // 차트 데이터 포맷
  const chartData = history.map(h => ({
    ...h,
    date: h.date.slice(5),  // MM-DD 형식으로 변환
    fullDate: h.date
  }));

  // 툴팁 커스텀
  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      const isPositive = data.returnRate >= 0;
      return (
        <div className="bg-[#1a1f2e] border border-slate-700 rounded-xl p-3 shadow-xl">
          <p className="text-xs text-slate-400 mb-1">{data.fullDate}</p>
          <p className={`text-lg font-black ${isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
            {isPositive ? '+' : ''}{data.returnRate.toFixed(2)}%
          </p>
          <p className="text-xs text-slate-500 mt-1">
            평가금: {formatNumber(data.totalValue)}원
          </p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="p-5 bg-[#0f121d]/50">
      {/* 수익률 추이 그래프 */}
      {history.length > 0 && (
        <div className="mb-6 bg-[#1a1f2e] rounded-xl p-4 border border-slate-800">
          <div className="flex items-center gap-2 mb-4">
            <LineChartIcon className="w-4 h-4 text-point-cyan" />
            <span className="text-xs text-slate-500 font-bold uppercase tracking-wider">포트폴리오 수익률 추이</span>
          </div>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="returnGradientPos" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                  </linearGradient>
                  <linearGradient id="returnGradientNeg" x1="0" y1="1" x2="0" y2="0">
                    <stop offset="5%" stopColor="#f43f5e" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="#f43f5e" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <XAxis 
                  dataKey="date" 
                  axisLine={false}
                  tickLine={false}
                  tick={{ fontSize: 10, fill: '#64748b' }}
                  interval="preserveStartEnd"
                />
                <YAxis 
                  axisLine={false}
                  tickLine={false}
                  tick={{ fontSize: 10, fill: '#64748b' }}
                  tickFormatter={(v) => `${v}%`}
                  domain={['auto', 'auto']}
                />
                <Tooltip content={<CustomTooltip />} />
                <ReferenceLine y={0} stroke="#475569" strokeDasharray="3 3" />
                <Area
                  type="monotone"
                  dataKey="returnRate"
                  stroke="none"
                  fill="url(#returnGradientPos)"
                  fillOpacity={1}
                />
                <Line
                  type="monotone"
                  dataKey="returnRate"
                  stroke={isProfit ? '#10b981' : '#f43f5e'}
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4, fill: isProfit ? '#10b981' : '#f43f5e' }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          {isLoadingHistory && (
            <div className="text-center text-xs text-slate-500 mt-2">
              <RefreshCw className="w-3 h-3 animate-spin inline mr-1" />
              히스토리 로딩 중...
            </div>
          )}
        </div>
      )}

      {/* Summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-[#1a1f2e] rounded-xl p-4 border border-slate-800">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">총 투자금</div>
          <div className="text-lg font-black text-white">{formatNumber(summary.totalInvested)}원</div>
        </div>
        <div className="bg-[#1a1f2e] rounded-xl p-4 border border-slate-800">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">평가금액</div>
          <div className="text-lg font-black text-white">{formatNumber(summary.totalCurrentValue)}원</div>
        </div>
        <div className="bg-[#1a1f2e] rounded-xl p-4 border border-slate-800">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">총 손익</div>
          <div className={`text-lg font-black flex items-center gap-1 ${isProfit ? 'text-emerald-400' : 'text-rose-400'}`}>
            {isProfit ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
            {isProfit ? '+' : ''}{formatNumber(summary.totalProfit)}원
          </div>
        </div>
        <div className={`rounded-xl p-4 border ${isProfit ? 'bg-emerald-500/10 border-emerald-500/30' : 'bg-rose-500/10 border-rose-500/30'}`}>
          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">수익률</div>
          <div className={`text-lg font-black ${isProfit ? 'text-emerald-400' : 'text-rose-400'}`}>
            {formatPercent(summary.returnRate)}
          </div>
        </div>
      </div>

      {/* Profit breakdown */}
      <div className="flex gap-4 mb-6">
        <div className="flex items-center gap-2 bg-[#1a1f2e] rounded-lg px-3 py-2 border border-slate-800">
          <Plus className="w-4 h-4 text-emerald-400" />
          <span className="text-sm text-slate-400">실현 손익:</span>
          <span className={`text-sm font-bold ${summary.totalRealizedProfit >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {summary.totalRealizedProfit >= 0 ? '+' : ''}{formatNumber(summary.totalRealizedProfit)}원
          </span>
        </div>
        <div className="flex items-center gap-2 bg-[#1a1f2e] rounded-lg px-3 py-2 border border-slate-800">
          <Minus className="w-4 h-4 text-violet-400" />
          <span className="text-sm text-slate-400">평가 손익:</span>
          <span className={`text-sm font-bold ${summary.totalUnrealizedProfit >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {summary.totalUnrealizedProfit >= 0 ? '+' : ''}{formatNumber(summary.totalUnrealizedProfit)}원
          </span>
        </div>
      </div>

      {/* Individual stocks */}
      <div className="space-y-2">
        <div className="text-xs text-slate-500 font-bold uppercase tracking-wider mb-3">종목별 수익률</div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[10px] text-slate-500 uppercase tracking-wider border-b border-slate-800">
                <th className="pb-3 pr-4">종목</th>
                <th className="pb-3 pr-4 text-right">보유수량</th>
                <th className="pb-3 pr-4 text-right">평균단가</th>
                <th className="pb-3 pr-4 text-right">현재가</th>
                <th className="pb-3 pr-4 text-right">평가손익</th>
                <th className="pb-3 text-right">수익률</th>
              </tr>
            </thead>
            <tbody>
              {returns.stocks.map((stock: StockReturns) => {
                const stockProfit = stock.returnRate >= 0;
                return (
                  <tr key={stock.stockId} className="border-b border-slate-800/50">
                    <td className="py-3 pr-4">
                      <div className="font-bold text-white">{stock.name}</div>
                      <div className="text-[10px] text-slate-500">{stock.symbol}</div>
                    </td>
                    <td className="py-3 pr-4 text-right text-slate-300 font-bold">
                      {formatNumber(stock.remainingQuantity)}주
                    </td>
                    <td className="py-3 pr-4 text-right text-slate-300">
                      {formatNumber(stock.avgBuyPrice)}원
                    </td>
                    <td className="py-3 pr-4 text-right text-white font-bold">
                      {formatNumber(stock.currentPrice)}원
                    </td>
                    <td className={`py-3 pr-4 text-right font-bold ${stockProfit ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {stockProfit ? '+' : ''}{formatNumber(stock.unrealizedProfit)}원
                    </td>
                    <td className={`py-3 text-right font-bold ${stockProfit ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {formatPercent(stock.returnRate)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

import React, { useState, useEffect } from 'react';
import { 
  TrendingUp, 
  TrendingDown,
  ArrowUpRight,
  ArrowDownRight,
  Users,
  Building2,
  Globe,
  RefreshCw
} from 'lucide-react';
import { MarketIndex, MarketInvestorTrend } from '../types';
import { 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  Tooltip, 
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
  Legend
} from 'recharts';

const API_BASE_URL = '/api';

export const Dashboard: React.FC = () => {
  const [indices, setIndices] = useState<{ kospi: MarketIndex; kosdaq: MarketIndex } | null>(null);
  const [investorTrends, setInvestorTrends] = useState<MarketInvestorTrend[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const loadData = async () => {
    setIsLoading(true);
    try {
      const [indicesRes, trendsRes] = await Promise.all([
        fetch(`${API_BASE_URL}/market-indices`),
        fetch(`${API_BASE_URL}/market-investor-trends`)
      ]);

      if (indicesRes.ok) {
        const indicesData = await indicesRes.json();
        setIndices(indicesData);
      }

      if (trendsRes.ok) {
        const trendsData = await trendsRes.json();
        setInvestorTrends(trendsData.data || []);
      }

      setLastUpdated(new Date());
    } catch (error) {
      console.error('대시보드 데이터 로딩 실패:', error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    // 1분마다 자동 새로고침
    const interval = setInterval(loadData, 60000);
    return () => clearInterval(interval);
  }, []);

  const formatNumber = (num: number) => {
    return new Intl.NumberFormat('ko-KR').format(num);
  };

  const formatDate = (dateStr: string) => {
    if (!dateStr || dateStr.length !== 8) return dateStr;
    return `${dateStr.slice(4, 6)}/${dateStr.slice(6, 8)}`;
  };

  const IndexCard: React.FC<{ index: MarketIndex; color: string }> = ({ index, color }) => {
    const isPositive = index.change >= 0;
    return (
      <div className={`bg-[#1a1f2e] border border-slate-800 rounded-2xl p-6 hover:border-${color}/30 transition-all`}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-white">{index.name}</h3>
          <div className={`p-2 rounded-lg ${isPositive ? 'bg-emerald-500/10' : 'bg-rose-500/10'}`}>
            {isPositive ? <TrendingUp className="w-5 h-5 text-emerald-400" /> : <TrendingDown className="w-5 h-5 text-rose-400" />}
          </div>
        </div>
        
        <div className="space-y-3">
          <div className="text-3xl font-black text-white">{formatNumber(Math.round(index.currentValue * 100) / 100)}</div>
          
          <div className="flex items-center gap-3">
            <span className={`flex items-center gap-1 text-sm font-bold ${isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
              {isPositive ? <ArrowUpRight className="w-4 h-4" /> : <ArrowDownRight className="w-4 h-4" />}
              {isPositive ? '+' : ''}{formatNumber(Math.round(index.change * 100) / 100)}
            </span>
            <span className={`text-sm font-bold px-2 py-0.5 rounded ${isPositive ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'}`}>
              {isPositive ? '+' : ''}{(Math.round(index.changePercent * 100) / 100).toFixed(2)}%
            </span>
          </div>

          <div className="grid grid-cols-3 gap-2 pt-3 border-t border-slate-800">
            <div>
              <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">시가</div>
              <div className="text-sm font-bold text-slate-300">{formatNumber(Math.round(index.open * 100) / 100)}</div>
            </div>
            <div>
              <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">고가</div>
              <div className="text-sm font-bold text-emerald-400">{formatNumber(Math.round(index.high * 100) / 100)}</div>
            </div>
            <div>
              <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">저가</div>
              <div className="text-sm font-bold text-rose-400">{formatNumber(Math.round(index.low * 100) / 100)}</div>
            </div>
          </div>
        </div>
      </div>
    );
  };

  if (isLoading && !indices) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex items-center gap-3 text-slate-400">
          <RefreshCw className="w-5 h-5 animate-spin" />
          <span className="font-bold">데이터를 불러오는 중...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-black text-white tracking-tight">시장 대시보드</h1>
          <p className="text-slate-500 font-bold mt-1">실시간 시장 지수 및 투자자 동향</p>
        </div>
        <button 
          onClick={loadData}
          disabled={isLoading}
          className="flex items-center gap-2 bg-[#1a1f2e] border border-slate-700 text-slate-400 hover:text-white hover:border-slate-600 px-4 py-2 rounded-xl text-sm font-bold transition-all disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          새로고침
        </button>
      </div>

      {lastUpdated && (
        <div className="text-[10px] text-slate-600 font-bold uppercase tracking-wider">
          마지막 업데이트: {lastUpdated.toLocaleTimeString('ko-KR')}
        </div>
      )}

      {/* Market Indices */}
      {indices && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <IndexCard index={indices.kospi} color="point-cyan" />
          <IndexCard index={indices.kosdaq} color="violet" />
        </div>
      )}

      {/* Investor Trends Chart */}
      <div className="bg-[#1a1f2e] border border-slate-800 rounded-2xl p-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-lg font-bold text-white">투자자별 매매동향 (KOSPI)</h3>
            <p className="text-sm text-slate-500 mt-1">최근 20일간 순매수 추이</p>
          </div>
          <div className="flex items-center gap-4 text-xs">
            <div className="flex items-center gap-2">
              <Users className="w-4 h-4 text-amber-400" />
              <span className="text-slate-400">개인</span>
            </div>
            <div className="flex items-center gap-2">
              <Globe className="w-4 h-4 text-emerald-400" />
              <span className="text-slate-400">외국인</span>
            </div>
            <div className="flex items-center gap-2">
              <Building2 className="w-4 h-4 text-violet-400" />
              <span className="text-slate-400">기관</span>
            </div>
          </div>
        </div>

        {investorTrends.length > 0 ? (
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={[...investorTrends].reverse().slice(-15)}>
              <XAxis 
                dataKey="date" 
                tickFormatter={formatDate}
                tick={{ fill: '#64748b', fontSize: 10 }}
                axisLine={{ stroke: '#334155' }}
              />
              <YAxis 
                tick={{ fill: '#64748b', fontSize: 10 }}
                axisLine={{ stroke: '#334155' }}
                tickFormatter={(v) => `${(v / 1000000).toFixed(0)}M`}
              />
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: '#1a1f2e', 
                  border: '1px solid #334155',
                  borderRadius: '12px',
                  fontSize: '12px'
                }}
                formatter={(value: number, name: string) => {
                  const labels: Record<string, string> = { individual: '개인', foreign: '외국인', institution: '기관' };
                  return [formatNumber(value), labels[name] || name];
                }}
                labelFormatter={(label) => `날짜: ${formatDate(label)}`}
              />
              <Bar dataKey="individual" fill="#f59e0b" radius={[4, 4, 0, 0]} />
              <Bar dataKey="foreign" fill="#10b981" radius={[4, 4, 0, 0]} />
              <Bar dataKey="institution" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-[300px] flex items-center justify-center text-slate-500">
            데이터를 불러올 수 없습니다.
          </div>
        )}
      </div>

      {/* Quick Stats */}
      {investorTrends.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {(() => {
            const latestTrend = investorTrends[0] || { individual: 0, foreign: 0, institution: 0 };
            return (
              <>
                <div className="bg-[#1a1f2e] border border-slate-800 rounded-xl p-4">
                  <div className="flex items-center gap-3 mb-2">
                    <Users className="w-5 h-5 text-amber-400" />
                    <span className="text-sm font-bold text-slate-400">개인 순매수</span>
                  </div>
                  <div className={`text-xl font-black ${latestTrend.individual >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {latestTrend.individual >= 0 ? '+' : ''}{formatNumber(latestTrend.individual)}
                  </div>
                </div>
                <div className="bg-[#1a1f2e] border border-slate-800 rounded-xl p-4">
                  <div className="flex items-center gap-3 mb-2">
                    <Globe className="w-5 h-5 text-emerald-400" />
                    <span className="text-sm font-bold text-slate-400">외국인 순매수</span>
                  </div>
                  <div className={`text-xl font-black ${latestTrend.foreign >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {latestTrend.foreign >= 0 ? '+' : ''}{formatNumber(latestTrend.foreign)}
                  </div>
                </div>
                <div className="bg-[#1a1f2e] border border-slate-800 rounded-xl p-4">
                  <div className="flex items-center gap-3 mb-2">
                    <Building2 className="w-5 h-5 text-violet-400" />
                    <span className="text-sm font-bold text-slate-400">기관 순매수</span>
                  </div>
                  <div className={`text-xl font-black ${latestTrend.institution >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {latestTrend.institution >= 0 ? '+' : ''}{formatNumber(latestTrend.institution)}
                  </div>
                </div>
              </>
            );
          })()}
        </div>
      )}
    </div>
  );
};

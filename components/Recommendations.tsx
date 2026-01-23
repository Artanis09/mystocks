import React, { useState, useEffect, useCallback, useRef } from 'react';
import { 
  TrendingUp, 
  Sparkles, 
  Target, 
  ArrowUpRight, 
  RefreshCw,
  Search,
  Zap,
  CheckCircle2,
  Calendar,
  AlertCircle,
  BrainCircuit,
  Cpu,
  BarChart2,
  ArrowUpDown,
  ShoppingCart,
  Banknote,
  Trash2,
  ChevronDown,
  ChevronRight,
  Loader2,
  Clock,
  Database,
  Download,
  Play,
  Moon,
  Wallet,
  TrendingDown,
  LineChart,
  Settings,
  CheckSquare,
  Square,
  DollarSign,
  Percent
} from 'lucide-react';
import { RecommendedStock } from '../types';

// Use relative path for API calls to work with domain/proxy
const API_BASE_URL = '/api';

interface RecommendationsProps {
  onStockClick: (stock: RecommendedStock) => void;
}

type SortKey = 'probability' | 'expected_return' | 'name' | 'current_price';
type SortDirection = 'asc' | 'desc';
type FilterTag = 'filter2';
type ModelName = 'model1' | 'model5';

interface SchedulerStatus {
  eod_done_today: boolean;
  intraday_done_today: boolean;
  inference_done_today: boolean;
  crawling_status: 'eod' | 'intraday' | null;
  crawling_start_time: string | null;
  crawling_error: string | null;
}

// 계좌 관련 타입
interface HoldingStock {
  code: string;
  name: string;
  quantity: number;
  avgPrice: number;
  currentPrice: number;
  evalAmount: number;
  profitLoss: number;
  profitRate: number;
  purchaseAmount: number;
}

interface AccountSummary {
  totalEvalAmount: number;
  totalPurchaseAmount: number;
  totalProfitLoss: number;
  totalProfitRate: number;
  depositBalance: number;
  availableCash: number;
  d2Deposit: number;
}

interface AssetHistory {
  time: string;
  totalAsset: number;
}

// 장 운영시간 체크 (08:00 ~ 20:00 사이만 true)
const isMarketHours = (): boolean => {
  const now = new Date();
  const hour = now.getHours();
  return hour >= 8 && hour < 20;
};

// AI Thinking Animation Component
const AIThinkingLoader: React.FC = () => (
  <div className="flex flex-col items-center justify-center py-20 animate-in fade-in duration-700">
    <div className="relative w-24 h-24 mb-8">
      <div className="absolute inset-0 border-4 border-point-cyan/20 rounded-full animate-[spin_3s_linear_infinite]"></div>
      <div className="absolute inset-0 border-4 border-t-point-cyan rounded-full animate-[spin_1.5s_linear_infinite]"></div>
      <div className="absolute inset-4 bg-[#1a1f2e] rounded-full flex items-center justify-center border border-slate-700 shadow-[0_0_30px_rgba(6,182,212,0.3)]">
        <BrainCircuit className="w-8 h-8 text-point-cyan animate-pulse" />
      </div>
    </div>
    <h3 className="text-xl font-black text-white mb-2 tracking-tight">AI Agent가 시장을 분석 중입니다</h3>
    <p className="text-slate-500 font-medium text-center max-w-md leading-relaxed">
      기술적 지표, 수급 데이터, 재무제표를 종합하여<br/>
      <span className="text-point-cyan font-bold">필터2(상승 확률 70% 이상 + 추가 리스크컷)</span>
      를 적용하여 추천 종목을 발굴하고 있습니다.
    </p>
  </div>
);

// 데이터 수집 중 메시지 컴포넌트
const CrawlingMessage: React.FC<{ status: SchedulerStatus }> = ({ status }) => (
  <div className="bg-amber-500/10 border border-amber-500/30 rounded-2xl p-8 text-center animate-in fade-in duration-500">
    <div className="w-16 h-16 bg-amber-500/20 rounded-full flex items-center justify-center mx-auto mb-5">
      <Database className="w-8 h-8 text-amber-400 animate-pulse" />
    </div>
    <h3 className="text-lg font-bold text-white mb-2">
      데이터 수집 중입니다
    </h3>
    <p className="text-slate-400 mb-4">
      {status.crawling_status === 'eod' ? '전체 종목 데이터(EOD)를' : '유니버스(시총 500억 이상) 데이터를'} 수집하고 있습니다.<br/>
      잠시만 기다려주세요.
    </p>
    <div className="flex items-center justify-center gap-2 text-sm text-amber-400">
      <Loader2 className="w-4 h-4 animate-spin" />
      <span>수집 시작: {status.crawling_start_time ? new Date(status.crawling_start_time).toLocaleTimeString('ko-KR') : '-'}</span>
    </div>
  </div>
);

// 추천 없음 메시지 컴포넌트
const NoRecommendationsMessage: React.FC<{ hasError: boolean; errorMsg?: string }> = ({ hasError, errorMsg }) => (
  <div className="bg-[#1a1f2e] border border-dashed border-slate-700 rounded-[2rem] py-16 px-10 text-center">
    <div className="w-16 h-16 bg-slate-800 rounded-full flex items-center justify-center mx-auto mb-5">
      {hasError ? (
        <AlertCircle className="w-8 h-8 text-rose-400" />
      ) : (
        <Clock className="w-8 h-8 text-slate-500 opacity-50" />
      )}
    </div>
    <h3 className="text-lg font-bold text-white mb-2">
      {hasError ? 'AI 분석 중 오류가 발생했습니다' : '오늘의 추천 종목이 아직 없습니다'}
    </h3>
    <p className="text-slate-500">
      {hasError ? errorMsg : '상단의 "AI 예측" 버튼을 눌러 분석을 시작하거나, 오후 3시 이후 자동 분석을 기다려주세요.'}
    </p>
  </div>
);

// 데이터 수집 패널 컴포넌트
interface DataCollectionPanelProps {
  schedulerStatus: SchedulerStatus | null;
  onRefreshStatus: () => void;
}

const DataCollectionPanel: React.FC<DataCollectionPanelProps> = ({ schedulerStatus, onRefreshStatus }) => {
  const today = new Date().toLocaleDateString('en-CA');
  const [startDate, setStartDate] = useState(today);
  const [endDate, setEndDate] = useState(today);
  const [mode, setMode] = useState<'eod' | 'intraday'>('eod');
  const [isExpanded, setIsExpanded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const isCrawling = schedulerStatus?.crawling_status != null;

  const handleStartCrawl = async () => {
    setError(null);
    setSuccessMessage(null);
    
    try {
      const response = await fetch(`${API_BASE_URL}/crawl`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          start_date: startDate,
          end_date: endDate,
          mode
        })
      });
      
      if (response.ok) {
        const data = await response.json();
        setSuccessMessage(data.message);
        onRefreshStatus();
      } else {
        const errData = await response.json();
        setError(errData.error || '데이터 수집 시작 실패');
      }
    } catch (err) {
      setError('서버 연결 실패');
    }
  };

  const handleTodayCrawl = async () => {
    setStartDate(today);
    setEndDate(today);
    setError(null);
    setSuccessMessage(null);
    
    try {
      const response = await fetch(`${API_BASE_URL}/crawl`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          start_date: today,
          end_date: today,
          mode: 'eod'
        })
      });
      
      if (response.ok) {
        const data = await response.json();
        setSuccessMessage(data.message);
        onRefreshStatus();
      } else {
        const errData = await response.json();
        setError(errData.error || '데이터 수집 시작 실패');
      }
    } catch (err) {
      setError('서버 연결 실패');
    }
  };

  // 자동수집 여부 체크 (mode에 'auto' 포함 여부)
  const isAutoCrawl = (schedulerStatus as any)?.last_crawl_mode?.includes('auto');

  // 소요시간 포맷팅
  const formatDuration = (seconds: number | null | undefined) => {
    if (!seconds) return null;
    if (seconds < 60) return `${Math.round(seconds)}초`;
    const mins = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return secs > 0 ? `${mins}분 ${secs}초` : `${mins}분`;
  };

  return (
    <div className="bg-[#1a1f2e] border border-slate-800 rounded-2xl mb-8 overflow-hidden">
      {/* Header - Always Visible */}
      <div 
        className="flex items-center justify-between p-4 cursor-pointer hover:bg-slate-800/30 transition-colors"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${
            isCrawling ? 'bg-amber-500/20' : 'bg-emerald-500/20'
          }`}>
            {isCrawling ? (
              <Loader2 className="w-5 h-5 text-amber-400 animate-spin" />
            ) : (
              <Database className="w-5 h-5 text-emerald-400" />
            )}
          </div>
          <div>
            <h3 className="text-white font-bold flex items-center gap-2">
              데이터 수집
              {isCrawling && (
                <span className="text-xs bg-amber-500/20 text-amber-400 px-2 py-0.5 rounded-full">
                  수집 중
                </span>
              )}
            </h3>
            <p className="text-xs text-slate-500">
              {isCrawling 
                ? `${schedulerStatus?.crawling_status === 'eod' ? 'EOD' : 'Intraday'} 모드로 수집 중...`
                : (schedulerStatus as any)?.data_start_date && (schedulerStatus as any)?.data_end_date
                  ? `${(schedulerStatus as any).data_start_date} ~ ${(schedulerStatus as any).data_end_date} (${(schedulerStatus as any).data_valid_days || 0}일)`
                  : '수동으로 주가 데이터를 수집합니다'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {!isExpanded && !isCrawling && (
            <button
              onClick={(e) => { e.stopPropagation(); handleTodayCrawl(); }}
              className="bg-emerald-500/10 hover:bg-emerald-500 text-emerald-400 hover:text-white border border-emerald-500/30 px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1"
            >
              <Play className="w-3 h-3" /> 오늘 데이터 수집
            </button>
          )}
          <div className="text-slate-400">
            {isExpanded ? <ChevronDown className="w-5 h-5" /> : <ChevronRight className="w-5 h-5" />}
          </div>
        </div>
      </div>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="p-4 pt-0 border-t border-slate-800 animate-in slide-in-from-top-2 duration-200">
          {/* 수집 중 상태 표시 */}
          {isCrawling && schedulerStatus && (
            <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4 mb-4">
              <div className="flex items-center gap-3">
                <div className="relative">
                  <div className="w-12 h-12 rounded-full border-4 border-amber-500/20"></div>
                  <div className="absolute inset-0 w-12 h-12 rounded-full border-4 border-t-amber-400 animate-spin"></div>
                  <Database className="absolute inset-0 m-auto w-5 h-5 text-amber-400" />
                </div>
                <div className="flex-1">
                  <p className="text-white font-bold">
                    {schedulerStatus.crawling_status === 'eod' ? 'EOD 전체 데이터' : 'Intraday 유니버스'} 수집 중
                  </p>
                  <p className="text-sm text-slate-400">
                    시작: {schedulerStatus.crawling_start_time 
                      ? new Date(schedulerStatus.crawling_start_time).toLocaleString('ko-KR')
                      : '-'}
                  </p>
                </div>
              </div>
              {schedulerStatus.crawling_error && (
                <div className="mt-3 p-2 bg-rose-500/10 rounded-lg text-sm text-rose-400">
                  오류: {schedulerStatus.crawling_error}
                </div>
              )}
            </div>
          )}

          {/* 데이터 상태 및 최근 수집 정보 */}
          {!isCrawling && (
            <div className="space-y-3 mb-4">
              {/* 데이터 범위 정보 */}
              {(schedulerStatus as any)?.data_start_date && (
                <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-3">
                  <div className="flex items-center gap-3 mb-2">
                    <div className="w-8 h-8 rounded-lg bg-blue-500/20 flex items-center justify-center">
                      <Database className="w-4 h-4 text-blue-400" />
                    </div>
                    <div className="flex-1">
                      <p className="text-sm text-white font-medium">수집된 데이터 범위</p>
                      <p className="text-xs text-slate-400">
                        {(schedulerStatus as any).data_start_date} ~ {(schedulerStatus as any).data_end_date}
                        {' • '}총 {(schedulerStatus as any).data_total_days}일 / 유효 {(schedulerStatus as any).data_valid_days}일
                      </p>
                    </div>
                  </div>
                  {/* 누락 날짜 표시 */}
                  {(schedulerStatus as any).data_missing_days?.length > 0 && (
                    <div className="mt-2 p-2 bg-amber-500/10 rounded-lg text-xs text-amber-400">
                      <span className="font-bold">누락 날짜:</span> {(schedulerStatus as any).data_missing_days.join(', ')}
                    </div>
                  )}
                  {/* 오류 표시 */}
                  {(schedulerStatus as any).data_errors?.length > 0 && (
                    <div className="mt-2 p-2 bg-rose-500/10 rounded-lg text-xs text-rose-400">
                      <span className="font-bold">오류:</span> {(schedulerStatus as any).data_errors.slice(0, 3).join(', ')}
                    </div>
                  )}
                </div>
              )}

              {/* 최근 수집 완료 정보 */}
              {(schedulerStatus as any)?.last_crawl_completed_at && (
                <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-3 flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-emerald-500/20 flex items-center justify-center">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  </div>
                  <div className="flex-1">
                    <p className="text-sm text-white font-medium">최근 수집 완료</p>
                    <p className="text-xs text-slate-400">
                      {new Date((schedulerStatus as any).last_crawl_completed_at).toLocaleString('ko-KR')}
                      {' • '}
                      <span className={`${
                        (schedulerStatus as any).last_crawl_mode?.includes('auto') 
                          ? 'text-blue-400' 
                          : 'text-amber-400'
                      }`}>
                        {(schedulerStatus as any).last_crawl_mode}
                      </span>
                      {(schedulerStatus as any).last_crawl_date_range && (
                        <> • {(schedulerStatus as any).last_crawl_date_range}</>
                      )}
                      {(schedulerStatus as any).last_crawl_duration && (
                        <> • 소요: {formatDuration((schedulerStatus as any).last_crawl_duration)}</>
                      )}
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* 수집 옵션 */}
          {!isCrawling && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                <div>
                  <label className="block text-xs text-slate-500 mb-1">시작일</label>
                  <input
                    type="date"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 text-white text-sm px-3 py-2 rounded-lg focus:outline-none focus:border-point-cyan"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-500 mb-1">종료일</label>
                  <input
                    type="date"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 text-white text-sm px-3 py-2 rounded-lg focus:outline-none focus:border-point-cyan"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-500 mb-1">수집 모드</label>
                  <select
                    value={mode}
                    onChange={(e) => setMode(e.target.value as 'eod' | 'intraday')}
                    className="w-full bg-slate-800 border border-slate-700 text-white text-sm px-3 py-2 rounded-lg focus:outline-none focus:border-point-cyan"
                  >
                    <option value="eod">EOD (전체 종목)</option>
                    <option value="intraday">Intraday (유니버스)</option>
                  </select>
                </div>
                <div className="flex items-end">
                  <button
                    onClick={handleStartCrawl}
                    className="w-full bg-point-cyan hover:bg-point-cyan/80 text-white font-bold py-2 px-4 rounded-lg transition-all flex items-center justify-center gap-2"
                  >
                    <Download className="w-4 h-4" />
                    수집 시작
                  </button>
                </div>
              </div>

              {/* 안내 메시지 */}
              <div className="text-xs text-slate-500 bg-slate-800/50 rounded-lg p-3">
                <p className="mb-1">• <strong>EOD 모드:</strong> 전체 종목(약 2,500개) 데이터 수집 - 15~30분 소요</p>
                <p>• <strong>Intraday 모드:</strong> 유니버스(시총 500억+) 종목만 수집 - 5~10분 소요</p>
              </div>
            </>
          )}

          {/* 에러/성공 메시지 */}
          {error && (
            <div className="mt-4 p-3 bg-rose-500/10 border border-rose-500/30 rounded-lg text-sm text-rose-400 flex items-center gap-2">
              <AlertCircle className="w-4 h-4" />
              {error}
            </div>
          )}
          {successMessage && (
            <div className="mt-4 p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-lg text-sm text-emerald-400 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4" />
              {successMessage}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// =============================
// 계좌 현황 패널 컴포넌트
// =============================
interface AccountPanelProps {
  onTotalAssetChange: (totalAsset: number) => void;
}

const AccountPanel: React.FC<AccountPanelProps> = ({ onTotalAssetChange }) => {
  const [isExpanded, setIsExpanded] = useState(true);  // 항상 열림 상태로 시작
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorHint, setErrorHint] = useState<string | null>(null);
  const [holdings, setHoldings] = useState<HoldingStock[]>([]);
  const [summary, setSummary] = useState<AccountSummary | null>(null);
  const [assetHistory, setAssetHistory] = useState<AssetHistory[]>([]);

  const formatPrice = (price: number) => {
    return new Intl.NumberFormat('ko-KR').format(price);
  };

  const fetchAccountBalance = async () => {
    setIsLoading(true);
    setError(null);
    setErrorHint(null);
    try {
      const response = await fetch(`${API_BASE_URL}/kis/account-balance`);
      const data = await response.json().catch(() => ({}));
      
      if (data.success) {
        setHoldings(data.holdings || []);
        setSummary(data.summary || null);
        setAssetHistory(data.assetHistory || []);
        // 총자산 변경 콜백
        const totalAsset = (data.summary?.totalEvalAmount || 0) + (data.summary?.depositBalance || 0);
        onTotalAssetChange(totalAsset);
      } else {
        setError(data.error || '계좌 조회 실패');
        setErrorHint(data.hint || null);
      }
    } catch (err) {
      setError('서버 연결 실패 - 백엔드 서버를 확인하세요');
    } finally {
      setIsLoading(false);
    }
  };

  // 컴포넌트 마운트 시에만 한 번 조회 (주기적 조회 없음)
  useEffect(() => {
    fetchAccountBalance();
  }, []);

  const totalAsset = summary ? summary.totalEvalAmount + summary.depositBalance : 0;
  const profitRate = summary?.totalProfitRate || 0;
  const isProfit = profitRate >= 0;

  return (
    <div className="bg-[#1a1f2e] border border-slate-800 rounded-2xl mb-8 overflow-hidden">
      {/* Header */}
      <div 
        className="flex items-center justify-between p-4 cursor-pointer hover:bg-slate-800/30 transition-colors"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${
            isProfit ? 'bg-emerald-500/20' : 'bg-rose-500/20'
          }`}>
            <Wallet className={`w-5 h-5 ${isProfit ? 'text-emerald-400' : 'text-rose-400'}`} />
          </div>
          <div>
            <h3 className="text-white font-bold flex items-center gap-2">
              한국투자증권 계좌
              {summary && (
                <span className={`text-xs px-2 py-0.5 rounded-full ${
                  isProfit ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'
                }`}>
                  {isProfit ? '+' : ''}{profitRate.toFixed(2)}%
                </span>
              )}
            </h3>
            <p className="text-xs text-slate-500">
              {summary ? `총자산: ${formatPrice(totalAsset)}원` : '계좌 연동 상태를 확인하세요'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {!isExpanded && summary && (
            <div className="text-right mr-4">
              <div className="text-sm font-bold text-white">{formatPrice(totalAsset)}원</div>
              <div className={`text-xs font-bold ${isProfit ? 'text-emerald-400' : 'text-rose-400'}`}>
                {isProfit ? '+' : ''}{formatPrice(summary.totalProfitLoss)}원
              </div>
            </div>
          )}
          {isLoading && <Loader2 className="w-4 h-4 text-slate-400 animate-spin" />}
          <div className="text-slate-400">
            {isExpanded ? <ChevronDown className="w-5 h-5" /> : <ChevronRight className="w-5 h-5" />}
          </div>
        </div>
      </div>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="p-4 pt-0 border-t border-slate-800 animate-in slide-in-from-top-2 duration-200">
          {error && (
            <div className="mb-4 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg">
              <div className="text-sm text-amber-400 flex items-center gap-2 font-medium">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                {error}
              </div>
              {errorHint && (
                <p className="text-xs text-slate-400 mt-2 ml-6">{errorHint}</p>
              )}
            </div>
          )}

          {/* 계좌 요약 */}
          {summary && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
              <div className="bg-slate-800/50 rounded-xl p-3">
                <p className="text-xs text-slate-500 mb-1">총자산</p>
                <p className="text-lg font-bold text-white">{formatPrice(totalAsset)}원</p>
              </div>
              <div className="bg-slate-800/50 rounded-xl p-3">
                <p className="text-xs text-slate-500 mb-1">예수금</p>
                <p className="text-lg font-bold text-white">{formatPrice(summary.depositBalance)}원</p>
              </div>
              <div className="bg-slate-800/50 rounded-xl p-3">
                <p className="text-xs text-slate-500 mb-1">총평가금액</p>
                <p className="text-lg font-bold text-white">{formatPrice(summary.totalEvalAmount)}원</p>
              </div>
              <div className="bg-slate-800/50 rounded-xl p-3">
                <p className="text-xs text-slate-500 mb-1">평가손익</p>
                <p className={`text-lg font-bold ${isProfit ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {isProfit ? '+' : ''}{formatPrice(summary.totalProfitLoss)}원
                </p>
                <p className={`text-xs ${isProfit ? 'text-emerald-400' : 'text-rose-400'}`}>
                  ({isProfit ? '+' : ''}{profitRate.toFixed(2)}%)
                </p>
              </div>
            </div>
          )}

          {/* 보유종목 리스트 */}
          {holdings.length > 0 && (
            <div className="bg-slate-800/30 rounded-xl p-3 mb-4">
              <h4 className="text-sm font-bold text-white mb-3 flex items-center gap-2">
                <BarChart2 className="w-4 h-4 text-point-cyan" />
                보유종목 ({holdings.length})
              </h4>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {holdings.map(stock => (
                  <div key={stock.code} className="flex items-center justify-between text-sm bg-slate-800/50 rounded-lg p-2">
                    <div>
                      <span className="font-bold text-white">{stock.name}</span>
                      <span className="text-xs text-slate-500 ml-2">{stock.code}</span>
                      <span className="text-xs text-slate-400 ml-2">{stock.quantity}주</span>
                    </div>
                    <div className="text-right">
                      <span className="text-white">{formatPrice(stock.evalAmount)}원</span>
                      <span className={`text-xs ml-2 ${stock.profitRate >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        ({stock.profitRate >= 0 ? '+' : ''}{stock.profitRate.toFixed(2)}%)
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 자산 변동 이력 (일자별 그래프) */}
          {assetHistory.length > 0 && (() => {
            // 일자별로 그룹핑 (마지막 값만 사용)
            const dailyData: Record<string, number> = {};
            assetHistory.forEach(h => {
              const dateKey = h.time.split(' ')[0]; // YYYY-MM-DD
              dailyData[dateKey] = h.totalAsset;
            });
            const sortedDates = Object.keys(dailyData).sort();
            const recentDates = sortedDates.slice(-14); // 최근 14일
            const values = recentDates.map(d => dailyData[d]);
            const minVal = Math.min(...values);
            const maxVal = Math.max(...values);
            const range = maxVal - minVal || 1;

            return (
              <div className="bg-slate-800/30 rounded-xl p-4">
                <h4 className="text-sm font-bold text-white mb-4 flex items-center gap-2">
                  <LineChart className="w-4 h-4 text-emerald-400" />
                  일자별 자산 변동
                  <span className="text-xs text-slate-500 font-normal ml-auto">최근 {recentDates.length}일</span>
                </h4>
                
                {/* 그래프 영역 */}
                <div className="relative h-32 mb-2">
                  {/* Y축 가이드라인 */}
                  <div className="absolute inset-0 flex flex-col justify-between pointer-events-none">
                    {[0, 1, 2].map(i => (
                      <div key={i} className="border-t border-slate-700/50 w-full" />
                    ))}
                  </div>
                  
                  {/* 막대 그래프 */}
                  <div className="relative h-full flex items-end gap-1">
                    {recentDates.map((date, idx) => {
                      const val = dailyData[date];
                      const heightPercent = ((val - minVal) / range) * 80 + 20; // 최소 20%
                      const prevVal = idx > 0 ? dailyData[recentDates[idx - 1]] : val;
                      const isUp = val >= prevVal;
                      
                      return (
                        <div
                          key={date}
                          className="flex-1 flex flex-col items-center justify-end group relative"
                        >
                          {/* 툴팁 */}
                          <div className="absolute bottom-full mb-2 bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-xs opacity-0 group-hover:opacity-100 transition-opacity z-10 whitespace-nowrap pointer-events-none">
                            <p className="text-slate-400">{date}</p>
                            <p className="text-white font-bold">{formatPrice(val)}원</p>
                          </div>
                          
                          {/* 막대 */}
                          <div
                            className={`w-full rounded-t-sm transition-all duration-300 ${
                              isUp ? 'bg-emerald-500/70 hover:bg-emerald-500' : 'bg-rose-500/70 hover:bg-rose-500'
                            }`}
                            style={{ height: `${heightPercent}%` }}
                          />
                        </div>
                      );
                    })}
                  </div>
                </div>
                
                {/* X축 레이블 */}
                <div className="flex gap-1">
                  {recentDates.map((date, idx) => (
                    <div key={date} className="flex-1 text-center">
                      <span className="text-[10px] text-slate-500">
                        {idx === 0 || idx === recentDates.length - 1 || idx % Math.ceil(recentDates.length / 5) === 0
                          ? date.slice(5) // MM-DD
                          : ''}
                      </span>
                    </div>
                  ))}
                </div>
                
                {/* 요약 */}
                <div className="mt-3 pt-3 border-t border-slate-700/50 flex justify-between text-xs">
                  <span className="text-slate-500">최저: <span className="text-white">{formatPrice(minVal)}원</span></span>
                  <span className="text-slate-500">최고: <span className="text-white">{formatPrice(maxVal)}원</span></span>
                  {values.length > 1 && (() => {
                    const change = values[values.length - 1] - values[0];
                    const changePercent = (change / values[0]) * 100;
                    const isPositive = change >= 0;
                    return (
                      <span className={isPositive ? 'text-emerald-400' : 'text-rose-400'}>
                        기간 {isPositive ? '+' : ''}{changePercent.toFixed(2)}%
                      </span>
                    );
                  })()}
                </div>
              </div>
            );
          })()}

          {/* 새로고침 버튼 */}
          <button
            onClick={fetchAccountBalance}
            disabled={isLoading}
            className="mt-4 w-full bg-point-cyan/10 hover:bg-point-cyan text-point-cyan hover:text-white border border-point-cyan/30 py-2 rounded-lg text-sm font-bold transition-all flex items-center justify-center gap-2 disabled:opacity-50"
          >
            {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            계좌 새로고침
          </button>
        </div>
      )}
    </div>
  );
};

export const Recommendations: React.FC<RecommendationsProps> = ({ onStockClick }) => {
  const [recommendationsByFilter, setRecommendationsByFilter] = useState<Record<FilterTag, RecommendedStock[]>>({
    filter2: []
  });
  const [isLoading, setIsLoading] = useState(true);
  const [predictingFilter, setPredictingFilter] = useState<FilterTag | null>(null);
  const [modelName, setModelName] = useState<ModelName>('model1');
  const [errorByFilter, setErrorByFilter] = useState<Record<FilterTag, string | null>>({
    filter2: null
  });
  
  // 스케줄러 상태
  const [schedulerStatus, setSchedulerStatus] = useState<SchedulerStatus | null>(null);
  
  // 일자별 접기/펼치기 상태 (기본: 오늘만 펼침)
  const [expandedDates, setExpandedDates] = useState<Set<string>>(new Set());
  
  // 실시간 가격 상태
  const [realtimePrices, setRealtimePrices] = useState<Record<string, { current_price: number; change_percent: number }>>({});
  
  // KIS API 상태 (실시간 가격 조회 가능 여부)
  const [kisApiStatus, setKisApiStatus] = useState<{ available: boolean; error: string | null }>({
    available: true,
    error: null
  });
  
  // 정렬 상태
  const [sortConfig, setSortConfig] = useState<{ key: SortKey; direction: SortDirection }>({
    key: 'expected_return',
    direction: 'desc'
  });

  // =============================
  // 계좌 및 매매 관련 상태
  // =============================
  const [totalAsset, setTotalAsset] = useState<number>(0);
  const [selectedStocks, setSelectedStocks] = useState<Set<string>>(new Set());
  const [buyRatio, setBuyRatio] = useState<number>(10); // 총자산 대비 매수 비율 (%)
  const [sellRatio, setSellRatio] = useState<number>(50); // 보유수량 대비 매도 비율 (%)
  const [showTradeSettings, setShowTradeSettings] = useState(false);
  const [isBatchOrdering, setIsBatchOrdering] = useState(false);
  const [batchOrderResult, setBatchOrderResult] = useState<any>(null);
  
  // AI 분석 상태
  const [stockAnalyses, setStockAnalyses] = useState<Record<string, string>>({});
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [aiService, setAiService] = useState<'openai' | 'gemini'>('openai');
  
  // Refs for visibility tracking
  const stockRowRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const observerRef = useRef<IntersectionObserver | null>(null);
  const visibleCodesRef = useRef<Set<string>>(new Set());
  const isFetchingPricesRef = useRef(false);

  // 오늘 날짜
  const today = new Date().toLocaleDateString('en-CA');

  // 스케줄러 상태 조회
  const fetchSchedulerStatus = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/scheduler/status`);
      if (response.ok) {
        const data = await response.json();
        setSchedulerStatus(data);
      }
    } catch (err) {
      console.error('Failed to fetch scheduler status:', err);
    }
  };

  // AI 종목 분석 호출
  const fetchStockAnalyses = async (stocks: { code: string; name: string }[]) => {
    if (stocks.length === 0) return;
    
    setIsAnalyzing(true);
    try {
      const response = await fetch(`${API_BASE_URL}/stock-analysis`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stocks, ai_service: aiService })
      });
      
      if (response.ok) {
        const data = await response.json();
        const analyses: Record<string, string> = {};
        for (const [code, info] of Object.entries(data.analyses || {})) {
          analyses[code] = (info as any).analysis || '';
        }
        setStockAnalyses(prev => ({ ...prev, ...analyses }));
      }
    } catch (err) {
      console.error('Failed to fetch stock analyses:', err);
    } finally {
      setIsAnalyzing(false);
    }
  };

  const fetchRecommendations = async (filterTag: FilterTag, refresh = false) => {
    if (refresh) {
      setPredictingFilter(filterTag);
      setErrorByFilter(prev => ({ ...prev, [filterTag]: null }));
      try {
        const response = await fetch(`${API_BASE_URL}/recommendations/predict?filter=${filterTag}&model=${modelName}`, {
          method: 'POST'
        });
        if (!response.ok) {
          let errData: any = null;
          try {
            errData = await response.json();
          } catch {
            // ignore
          }
          const baseMsg = errData?.error || 'Prediction failed';
          const backendPython = errData?.backend_python ? `\n\nbackend_python: ${errData.backend_python}` : '';
          const howToFix = Array.isArray(errData?.how_to_fix) ? `\n\nHow to fix:\n- ${errData.how_to_fix.join('\n- ')}` : '';
          throw new Error(`${baseMsg}${backendPython}${howToFix}`);
        }
        
        // 예측 성공 후 추천 목록 다시 조회
        const recResponse = await fetch(`${API_BASE_URL}/recommendations?filter=${filterTag}&model=${modelName}`);
        if (recResponse.ok) {
          const data = await recResponse.json();
          const processed = data.map((item: any) => ({
            ...item,
            close: item.base_price || item.close,
          }));
          setRecommendationsByFilter(prev => ({ ...prev, [filterTag]: processed }));
          
          setExpandedDates(prev => {
            const newSet = new Set(prev);
            newSet.add(today);
            return newSet;
          });
          
          // AI 예측 완료 후 오늘 추천 종목 5개에 대해 OpenAI 분석 호출
          const todayStocks = processed.filter((s: any) => s.date === today).slice(0, 5);
          if (todayStocks.length > 0) {
            fetchStockAnalyses(todayStocks.map((s: any) => ({ code: s.code, name: s.name })));
          }
        }
      } catch (err: any) {
        setErrorByFilter(prev => ({ ...prev, [filterTag]: err.message || 'AI 분석 중 오류가 발생했습니다' }));
        console.error(err);
      } finally {
        setPredictingFilter(null);
      }
      return;
    }

    // GET 조회
    try {
      const response = await fetch(`${API_BASE_URL}/recommendations?filter=${filterTag}&model=${modelName}`);
      if (response.ok) {
        // KIS API 상태 헤더 읽기
        const kisAvailable = response.headers.get('X-KIS-Available') !== 'false';
        const kisError = response.headers.get('X-KIS-Error');
        setKisApiStatus({ available: kisAvailable, error: kisError });
        
        const data = await response.json();
        const processed = data.map((item: any) => ({
          ...item,
          close: item.base_price || item.close,
        }));
        setRecommendationsByFilter(prev => ({ ...prev, [filterTag]: processed }));
        
        // 오늘 날짜는 기본 펼침
        setExpandedDates(prev => {
          const newSet = new Set(prev);
          newSet.add(today);
          return newSet;
        });
      } else {
        const errData = await response.json();
        setErrorByFilter(prev => ({ ...prev, [filterTag]: errData.error || 'Failed to fetch recommendations' }));
      }
    } catch (err) {
      setErrorByFilter(prev => ({ ...prev, [filterTag]: 'Connection to backend failed' }));
      console.error(err);
    }
  };

  // 실시간 가격 조회 (보이는 종목만, 장 운영시간에만)
  const fetchRealtimePrices = useCallback(async () => {
    // 장외 시간 (20:00 ~ 08:00)에는 실시간 조회 안함
    if (!isMarketHours()) {
      return;
    }
    
    // 이미 요청 중이면 스킵
    if (isFetchingPricesRef.current) return;
    
    const codes = Array.from(visibleCodesRef.current).slice(0, 20);
    if (codes.length === 0) return;
    
    isFetchingPricesRef.current = true;
    try {
      const response = await fetch(`${API_BASE_URL}/realtime-prices`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ codes })
      });
      if (response.ok) {
        const data = await response.json();
        setRealtimePrices(prev => ({ ...prev, ...data }));
      }
    } catch (err) {
      console.error('Failed to fetch realtime prices:', err);
    } finally {
      isFetchingPricesRef.current = false;
    }
  }, []);

  // 초기 로드
  useEffect(() => {
    setIsLoading(true);
    Promise.all([
      fetchRecommendations('filter2', false),
      fetchSchedulerStatus()
    ]).finally(() => setIsLoading(false));
  }, [modelName]);

  // 스케줄러 상태 주기적 조회
  useEffect(() => {
    const interval = setInterval(() => {
      fetchSchedulerStatus();
    }, schedulerStatus?.crawling_status ? 5000 : 30000);
    return () => clearInterval(interval);
  }, [schedulerStatus?.crawling_status]);

  // 실시간 가격 5초마다 폴링 (한 번만 설정)
  useEffect(() => {
    // 초기 로드 후 1초 뒤에 첫 조회 (데이터 로드 대기)
    const initialTimeout = setTimeout(fetchRealtimePrices, 1000);
    const interval = setInterval(fetchRealtimePrices, 5000);
    return () => {
      clearTimeout(initialTimeout);
      clearInterval(interval);
    };
  }, []);

  // IntersectionObserver 설정
  useEffect(() => {
    observerRef.current = new IntersectionObserver(
      (entries) => {
        entries.forEach(entry => {
          const code = entry.target.getAttribute('data-code');
          if (code) {
            // ref를 직접 수정 (상태 변경 없음 = 리렌더링 없음)
            if (entry.isIntersecting) {
              visibleCodesRef.current.add(code);
            } else {
              visibleCodesRef.current.delete(code);
            }
          }
        });
      },
      { threshold: 0.1 }
    );
    return () => {
      observerRef.current?.disconnect();
    };
  }, []);

  // 종목 행 ref 등록
  const setStockRowRef = useCallback((code: string, el: HTMLDivElement | null) => {
    if (el) {
      stockRowRefs.current.set(code, el);
      observerRef.current?.observe(el);
    } else {
      const existing = stockRowRefs.current.get(code);
      if (existing) {
        observerRef.current?.unobserve(existing);
        stockRowRefs.current.delete(code);
      }
    }
  }, []);

  // 정렬 핸들러
  const handleSort = (key: SortKey) => {
    setSortConfig(prev => ({
      key,
      direction: prev.key === key && prev.direction === 'desc' ? 'asc' : 'desc'
    }));
  };

  // 일자 접기/펼치기 토글
  const toggleDateExpansion = (date: string) => {
    setExpandedDates(prev => {
      const newSet = new Set(prev);
      if (newSet.has(date)) {
        newSet.delete(date);
      } else {
        newSet.add(date);
      }
      return newSet;
    });
  };

  // 유틸리티 함수들 (핸들러에서 사용하므로 먼저 정의)
  const formatPrice = (price?: number) => {
    if (price === undefined || price === null) return '-';
    return new Intl.NumberFormat('ko-KR').format(price);
  };

  const formatMarketCap = (cap: number) => {
    const eok = Math.round(cap / 100000000);
    if (eok >= 10000) {
      return (eok / 10000).toFixed(1) + '조';
    }
    return eok + '억';
  };

  const formatPercent = (val: number) => {
    return (val * 100).toFixed(1) + '%';
  };

  const formatReturnRate = (val?: number) => {
    if (val === undefined) return '-';
    return val.toFixed(2) + '%';
  };

  // =============================
  // 종목 선택 핸들러
  // =============================
  const handleSelectStock = (e: React.MouseEvent, code: string) => {
    e.stopPropagation();
    setSelectedStocks(prev => {
      const newSet = new Set(prev);
      if (newSet.has(code)) {
        newSet.delete(code);
      } else {
        newSet.add(code);
      }
      return newSet;
    });
  };

  const handleSelectAll = (stocks: RecommendedStock[]) => {
    const codes = stocks.map(s => s.code);
    const allSelected = codes.every(c => selectedStocks.has(c));
    
    if (allSelected) {
      // 모두 해제
      setSelectedStocks(prev => {
        const newSet = new Set(prev);
        codes.forEach(c => newSet.delete(c));
        return newSet;
      });
    } else {
      // 모두 선택
      setSelectedStocks(prev => {
        const newSet = new Set(prev);
        codes.forEach(c => newSet.add(c));
        return newSet;
      });
    }
  };

  // =============================
  // 개별 매수/매도 핸들러
  // =============================
  const handleBuy = async (e: React.MouseEvent, stock: RecommendedStock) => {
    e.stopPropagation();
    
    if (totalAsset <= 0) {
      alert('먼저 계좌 정보를 새로고침하여 총자산을 확인하세요.');
      return;
    }

    // 매수 수량 계산
    const buyAmount = totalAsset * (buyRatio / 100);
    const currentPrice = realtimePrices[stock.code]?.current_price || stock.base_price || 0;
    if (currentPrice <= 0) {
      alert('현재가를 확인할 수 없습니다.');
      return;
    }
    const quantity = Math.floor(buyAmount / currentPrice);

    if (quantity <= 0) {
      alert(`매수 가능 수량이 없습니다.\n(총자산의 ${buyRatio}% = ${formatPrice(buyAmount)}원, 현재가 ${formatPrice(currentPrice)}원)`);
      return;
    }

    if (!window.confirm(`[시장가 매수 확인]\n종목명: ${stock.name} (${stock.code})\n현재가: ${formatPrice(currentPrice)}원\n매수비율: 총자산의 ${buyRatio}%\n예상금액: ${formatPrice(buyAmount)}원\n매수수량: ${quantity}주\n\n매수하시겠습니까?`)) {
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/kis/order`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: stock.code,
          quantity,
          orderType: 'buy'
        })
      });

      const data = await response.json();
      if (data.success) {
        alert(`매수 주문 완료!\n주문번호: ${data.order?.orderNo}\n종목: ${stock.name}\n수량: ${quantity}주`);
      } else {
        alert(`매수 실패: ${data.error}`);
      }
    } catch (err) {
      alert('매수 주문 중 오류가 발생했습니다.');
    }
  };

  const handleSell = async (e: React.MouseEvent, stock: RecommendedStock) => {
    e.stopPropagation();
    
    // 보유수량 확인 필요 (실제로는 계좌에서 조회)
    const holdingQuantity = (stock as any).holdingQuantity || 0;
    if (holdingQuantity <= 0) {
      alert('해당 종목의 보유 수량이 없거나, 계좌를 새로고침하여 보유 정보를 확인하세요.');
      return;
    }

    const sellQuantity = Math.floor(holdingQuantity * (sellRatio / 100));
    if (sellQuantity <= 0) {
      alert(`매도 가능 수량이 없습니다.\n(보유 ${holdingQuantity}주의 ${sellRatio}%)`);
      return;
    }

    const currentPrice = realtimePrices[stock.code]?.current_price || stock.base_price || 0;

    if (!window.confirm(`[시장가 매도 확인]\n종목명: ${stock.name} (${stock.code})\n현재가: ${formatPrice(currentPrice)}원\n매도비율: 보유의 ${sellRatio}%\n보유수량: ${holdingQuantity}주\n매도수량: ${sellQuantity}주\n\n매도하시겠습니까?`)) {
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/kis/order`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: stock.code,
          quantity: sellQuantity,
          orderType: 'sell'
        })
      });

      const data = await response.json();
      if (data.success) {
        alert(`매도 주문 완료!\n주문번호: ${data.order?.orderNo}\n종목: ${stock.name}\n수량: ${sellQuantity}주`);
      } else {
        alert(`매도 실패: ${data.error}`);
      }
    } catch (err) {
      alert('매도 주문 중 오류가 발생했습니다.');
    }
  };

  // =============================
  // 일괄 매수/매도 핸들러
  // =============================
  const handleBatchBuy = async () => {
    if (selectedStocks.size === 0) {
      alert('선택된 종목이 없습니다.');
      return;
    }

    if (totalAsset <= 0) {
      alert('먼저 계좌 정보를 새로고침하여 총자산을 확인하세요.');
      return;
    }

    const selectedList = recommendationsByFilter.filter2.filter(s => selectedStocks.has(s.code));
    const orders: Array<{ code: string; quantity: number; orderType: string; name: string }> = [];

    // 각 종목별 매수 수량 계산
    const perStockRatio = buyRatio / selectedStocks.size; // 균등 분배
    const buyAmountPerStock = totalAsset * (perStockRatio / 100);

    for (const stock of selectedList) {
      const currentPrice = realtimePrices[stock.code]?.current_price || stock.base_price || 0;
      if (currentPrice > 0) {
        const quantity = Math.floor(buyAmountPerStock / currentPrice);
        if (quantity > 0) {
          orders.push({ code: stock.code, quantity, orderType: 'buy', name: stock.name });
        }
      }
    }

    if (orders.length === 0) {
      alert('매수 가능한 종목이 없습니다.');
      return;
    }

    const orderSummary = orders.map(o => `${o.name}: ${o.quantity}주`).join('\n');
    if (!window.confirm(`[일괄 시장가 매수]\n총 ${orders.length}종목\n매수비율: 총자산의 ${buyRatio}% (균등배분)\n\n${orderSummary}\n\n진행하시겠습니까?`)) {
      return;
    }

    setIsBatchOrdering(true);
    setBatchOrderResult(null);

    try {
      const response = await fetch(`${API_BASE_URL}/kis/batch-order`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ orders })
      });

      const data = await response.json();
      setBatchOrderResult(data);

      if (data.success) {
        alert(`일괄 매수 완료!\n성공: ${data.summary?.success}개\n실패: ${data.summary?.failed}개`);
        setSelectedStocks(new Set()); // 선택 해제
      } else {
        alert(`일괄 매수 실패: ${data.error}`);
      }
    } catch (err) {
      alert('일괄 매수 중 오류가 발생했습니다.');
    } finally {
      setIsBatchOrdering(false);
    }
  };

  const handleBatchSell = async () => {
    if (selectedStocks.size === 0) {
      alert('선택된 종목이 없습니다.');
      return;
    }

    alert('일괄 매도는 보유종목 정보가 필요합니다. 계좌 패널에서 확인하세요.');
    // 실제 구현시에는 보유종목과 매칭하여 매도 수량 계산
  };

  const handleDeleteList = async (e: React.MouseEvent, date: string, filterTag: FilterTag) => {
    e.stopPropagation();
    if (!window.confirm(`${date} 날짜의 추천 목록을 삭제하시겠습니까?`)) {
      return;
    }
    try {
      const response = await fetch(`${API_BASE_URL}/recommendations?date=${date}&filter=${filterTag}&model=${modelName}`, {
        method: 'DELETE'
      });
      if (response.ok) {
        setRecommendationsByFilter(prev => ({
          ...prev,
          [filterTag]: prev[filterTag].filter(s => s.date !== date)
        }));
      } else {
        const data = await response.json();
        alert(`삭제 실패: ${data.error}`);
      }
    } catch (err) {
      console.error(err);
      alert('삭제 중 오류가 발생했습니다.');
    }
  };

  // 개별 종목 삭제
  const handleDeleteStock = async (e: React.MouseEvent, stock: RecommendedStock) => {
    e.stopPropagation();
    if (!window.confirm(`${stock.name} (${stock.code})을(를) 삭제하시겠습니까?`)) {
      return;
    }
    try {
      const response = await fetch(`${API_BASE_URL}/recommendations/${stock.id}`, {
        method: 'DELETE'
      });
      if (response.ok) {
        setRecommendationsByFilter(prev => ({
          ...prev,
          filter2: prev.filter2.filter(s => s.id !== stock.id)
        }));
      } else {
        const data = await response.json();
        alert(`삭제 실패: ${data.error}`);
      }
    } catch (err) {
      console.error(err);
      alert('삭제 중 오류가 발생했습니다.');
    }
  };

  // 크롤링 중 확인
  const isCrawling = schedulerStatus?.crawling_status != null;

  if (predictingFilter) {
    return (
      <div className="p-8 max-w-7xl mx-auto">
        <AIThinkingLoader />
      </div>
    );
  }

  const renderSection = (filterTag: FilterTag, title: string, subtitle: string) => {
    const recommendations = recommendationsByFilter[filterTag] || [];
    const error = errorByFilter[filterTag];

    // 날짜별로 그룹핑
    const grouped = recommendations.reduce((acc, stock) => {
      const date = stock.date || 'Unknown';
      if (!acc[date]) acc[date] = [];
      acc[date].push(stock);
      return acc;
    }, {} as Record<string, RecommendedStock[]>);

    // 날짜 내림차순 정렬
    const sortedDates = Object.keys(grouped).sort((a, b) => new Date(b).getTime() - new Date(a).getTime());

    // 오늘 추천 존재 여부
    const hasTodayRecommendations = (grouped[today]?.length || 0) > 0;

    return (
      <div className="space-y-6">
        <div className="flex items-start justify-between gap-6">
          <div>
            <h2 className="text-xl font-black text-white flex items-center gap-2">
              {title}
            </h2>
            <p className="text-slate-500 mt-1 font-medium">{subtitle}</p>
          </div>
        </div>

        {error && (
          <div className="bg-rose-500/10 border border-rose-500/30 rounded-2xl p-4 text-center animate-in slide-in-from-top-2">
            <p className="text-rose-400 font-bold flex items-center justify-center gap-2">
              <AlertCircle className="w-5 h-5" />
              {error}
            </p>
          </div>
        )}

        {isLoading ? (
          <div className="space-y-4">
            {[1, 2].map(i => (
              <div key={i} className="h-24 bg-[#1a1f2e] rounded-2xl animate-pulse" />
            ))}
          </div>
        ) : isCrawling && schedulerStatus ? (
          <CrawlingMessage status={schedulerStatus} />
        ) : recommendations.length === 0 ? (
          <NoRecommendationsMessage hasError={!!error} errorMsg={error || undefined} />
        ) : (
          <div className="space-y-4 animate-in fade-in duration-500">
            {/* 오늘 추천이 없으면 안내 메시지 */}
            {!hasTodayRecommendations && (
              <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-4 mb-4">
                <p className="text-slate-400 text-sm flex items-center gap-2">
                  <Clock className="w-4 h-4" />
                  오늘({today})의 추천 종목이 아직 없습니다. "AI 예측" 버튼을 눌러 분석을 시작하세요.
                </p>
              </div>
            )}

            {sortedDates.map(date => {
              const isToday = date === today;
              const isExpanded = expandedDates.has(date);
              let stocks = [...grouped[date]];

              // 정렬 적용
              stocks.sort((a, b) => {
                let valA: any = a[sortConfig.key];
                let valB: any = b[sortConfig.key];

                if (sortConfig.key === 'current_price') {
                  const priceA = realtimePrices[a.code]?.current_price ?? a.current_price ?? 0;
                  const priceB = realtimePrices[b.code]?.current_price ?? b.current_price ?? 0;
                  valA = priceA;
                  valB = priceB;
                }

                if (valA < valB) return sortConfig.direction === 'asc' ? -1 : 1;
                if (valA > valB) return sortConfig.direction === 'asc' ? 1 : -1;
                return 0;
              });

              return (
                <div key={`${filterTag}_${date}`} className="relative">
                  {/* Date Header - Clickable */}
                  <div
                    className="flex items-center gap-4 mb-2 cursor-pointer hover:bg-slate-800/30 rounded-xl p-2 -ml-2 transition-colors"
                    onClick={() => toggleDateExpansion(date)}
                  >
                    <div className="text-slate-400">
                      {isExpanded ? <ChevronDown className="w-5 h-5" /> : <ChevronRight className="w-5 h-5" />}
                    </div>
                    <div className={`px-4 py-1.5 rounded-lg text-sm font-black flex items-center gap-2 ${
                      isToday ? 'bg-point-cyan text-white shadow-lg shadow-point-cyan/20' : 'bg-slate-800 text-slate-400'
                    }`}>
                      <Calendar className="w-4 h-4" />
                      {date}
                    </div>
                    <div className="text-sm text-slate-500">{stocks.length}종목</div>
                    <div className="h-px bg-slate-800 flex-1"></div>

                    {/* Delete Date Group Button */}
                    <button
                      onClick={(e) => handleDeleteList(e, date, filterTag)}
                      className="p-2 hover:bg-rose-500/10 text-slate-500 hover:text-rose-400 rounded-lg transition-all"
                      title={`${date} 목록 삭제`}
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>

                  {/* Collapsible Content */}
                  {isExpanded && (
                    <div className="bg-[#1a1f2e] border border-slate-800 rounded-2xl overflow-hidden shadow-xl animate-in slide-in-from-top-2 duration-200">
                      {/* Table Header */}
                      <div className="grid grid-cols-12 gap-4 p-4 bg-[#151925] border-b border-slate-800 text-xs font-bold text-slate-500 uppercase tracking-wider select-none">
                        <div className="col-span-1 flex items-center justify-center gap-2">
                          <button
                            onClick={(e) => { e.stopPropagation(); handleSelectAll(stocks); }}
                            className="hover:text-point-cyan transition-colors"
                            title="전체 선택/해제"
                          >
                            {stocks.every(s => selectedStocks.has(s.code)) 
                              ? <CheckSquare className="w-4 h-4 text-point-cyan" />
                              : <Square className="w-4 h-4" />
                            }
                          </button>
                        </div>
                        <div
                          className="col-span-3 pl-2 cursor-pointer hover:text-white flex items-center gap-1"
                          onClick={() => handleSort('name')}
                        >
                          종목명 {sortConfig.key === 'name' && <ArrowUpDown className="w-3 h-3" />}
                        </div>
                        <div className="col-span-2 text-right">추천가</div>
                        <div
                          className="col-span-2 text-right cursor-pointer hover:text-white flex items-center justify-end gap-1"
                          onClick={() => handleSort('current_price')}
                        >
                          현재가 {sortConfig.key === 'current_price' && <ArrowUpDown className="w-3 h-3" />}
                        </div>
                        <div
                          className="col-span-1 text-right cursor-pointer hover:text-white flex items-center justify-end gap-1"
                          onClick={() => handleSort('probability')}
                        >
                          확률 {sortConfig.key === 'probability' && <ArrowUpDown className="w-3 h-3" />}
                        </div>
                        <div
                          className="col-span-1 text-right cursor-pointer hover:text-white flex items-center justify-end gap-1"
                          onClick={() => handleSort('expected_return')}
                        >
                          기대수익 {sortConfig.key === 'expected_return' && <ArrowUpDown className="w-3 h-3" />}
                        </div>
                        <div className="col-span-2 text-center">액션</div>
                      </div>

                      {/* Table Body */}
                      {stocks.map((stock, idx) => {
                        // 실시간 가격 (있으면 사용, 없으면 기존 값)
                        const rtPrice = realtimePrices[stock.code];
                        const currentPrice = rtPrice?.current_price ?? stock.current_price ?? stock.base_price;
                        const currentChange = rtPrice?.change_percent ?? stock.current_change ?? 0;
                        // 가격 출처: 'realtime' | 'local' | 'base'
                        const priceSource = rtPrice ? 'realtime' : (stock as any).price_source || 'base';

                        const returnRate = stock.base_price > 0
                          ? (currentPrice - stock.base_price) / stock.base_price * 100
                          : 0;
                        const isPositive = returnRate >= 0;

                        return (
                          <div
                            key={`${filterTag}_${stock.id || stock.code}_${idx}`}
                            ref={(el) => setStockRowRef(stock.code, el)}
                            data-code={stock.code}
                            className={`border-b border-slate-800/50 hover:bg-slate-800/50 transition-colors group ${
                              selectedStocks.has(stock.code) ? 'bg-point-cyan/5' : ''
                            }`}
                          >
                            {/* 종목 정보 행 */}
                            <div 
                              onClick={() => onStockClick(stock)}
                              className="grid grid-cols-12 gap-4 p-4 cursor-pointer items-center"
                            >
                              {/* Checkbox */}
                              <div className="col-span-1 flex justify-center">
                                <button
                                  onClick={(e) => handleSelectStock(e, stock.code)}
                                  className="hover:scale-110 transition-transform"
                                >
                                  {selectedStocks.has(stock.code) 
                                    ? <CheckSquare className="w-5 h-5 text-point-cyan" />
                                    : <Square className="w-5 h-5 text-slate-600 hover:text-slate-400" />
                                  }
                                </button>
                              </div>

                              {/* Name & Code */}
                              <div className="col-span-3 flex flex-col justify-center pl-2">
                                <div className="flex items-center gap-2">
                                  <span className="text-white font-bold group-hover:text-point-cyan transition-colors truncate">{stock.name}</span>
                                  {stock.probability >= 0.9 && (
                                    <Zap className="w-3 h-3 text-yellow-400 fill-yellow-400" />
                                  )}
                                </div>
                                <span className="text-xs text-slate-500 font-mono">{stock.code} · {formatMarketCap(stock.market_cap)}</span>
                              </div>

                              {/* Base Price */}
                              <div className="col-span-2 text-right text-slate-400 font-mono text-sm">
                                {formatPrice(stock.base_price)}원
                              </div>

                              {/* Current Price & Return Rate */}
                              <div className="col-span-2 text-right">
                                <div className="font-mono text-sm font-bold text-white mb-0.5 flex items-center justify-end gap-1">
                                  {formatPrice(currentPrice)}원
                                  {priceSource === 'realtime' && (
                                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" title="실시간" />
                                  )}
                                  {priceSource === 'local' && (
                                    <span className="w-2 h-2 rounded-full bg-amber-400" title="장중" />
                                  )}
                                  {priceSource === 'base' && (
                                    <span className="w-2 h-2 rounded-full bg-slate-500" title="기준가" />
                                  )}
                                </div>
                                <div className="flex flex-col items-end">
                                  <div className={`text-[10px] font-bold ${
                                    currentChange >= 0 ? 'text-emerald-400' : 'text-rose-400'
                                  }`}>
                                    당일 {currentChange >= 0 ? '+' : ''}{currentChange.toFixed(2)}%
                                  </div>
                                  <div className={`text-xs font-bold px-1.5 py-0.5 rounded-md mt-0.5 ${
                                    isPositive ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'
                                  }`}>
                                    추천대비 {isPositive ? '+' : ''}{returnRate.toFixed(2)}%
                                  </div>
                                </div>
                              </div>

                              {/* Probability */}
                              <div className="col-span-1 text-right">
                                <span className="text-sm font-bold text-point-cyan">{formatPercent(stock.probability)}</span>
                              </div>

                              {/* Expected Return */}
                              <div className="col-span-1 text-right">
                                <span className="text-sm font-bold text-emerald-400">+{formatPercent(stock.expected_return)}</span>
                              </div>

                              {/* Action Buttons */}
                              <div className="col-span-2 flex items-center justify-center gap-1">
                                <button
                                  onClick={(e) => handleDeleteStock(e, stock)}
                                  className="p-1.5 hover:bg-slate-700 text-slate-500 hover:text-slate-300 rounded-lg transition-all"
                                  title="삭제"
                                >
                                  <Trash2 className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  onClick={(e) => handleSell(e, stock)}
                                  className="bg-rose-500/10 hover:bg-rose-500 text-rose-400 hover:text-white border border-rose-500/30 px-2 py-1 rounded-lg text-xs font-bold transition-all flex items-center gap-1"
                                >
                                  <Banknote className="w-3 h-3" /> 매도
                                </button>
                                <button
                                  onClick={(e) => handleBuy(e, stock)}
                                  className="bg-point-cyan/10 hover:bg-point-cyan text-point-cyan hover:text-white border border-point-cyan/30 px-2 py-1 rounded-lg text-xs font-bold transition-all flex items-center gap-1"
                                >
                                  <ShoppingCart className="w-3 h-3" /> 매수
                                </button>
                              </div>
                            </div>
                            
                            {/* AI 분석 결과 (전체 넓이) */}
                            {(stock.ai_analysis || stockAnalyses[stock.code] || (isAnalyzing && date === today && idx < 5)) && (
                              <div className="px-4 pb-3">
                                {(stock.ai_analysis || stockAnalyses[stock.code]) ? (
                                  <div className={`text-xs leading-relaxed p-3 rounded-lg ${
                                    (stock.ai_analysis || stockAnalyses[stock.code]).includes('매매금지') 
                                      ? 'text-rose-300 bg-rose-500/10 border border-rose-500/30' 
                                      : 'text-slate-300 bg-slate-800/50 border border-slate-700'
                                  }`}>
                                    <div className="flex items-start gap-2">
                                      <div className="flex flex-col items-center gap-1">
                                        <BrainCircuit className="w-4 h-4 mt-0.5 flex-shrink-0 text-violet-400" />
                                        {(stock.ai_service || (stockAnalyses[stock.code] && aiService)) && (
                                          <span className="text-[8px] text-violet-500/70 font-bold uppercase leading-none">
                                            {stock.ai_service || aiService}
                                          </span>
                                        )}
                                      </div>
                                      <div className="flex-1">
                                        {(stock.ai_analysis || stockAnalyses[stock.code]).split('\n').map((line, i) => (
                                          <div key={i} className="mb-0.5">{line}</div>
                                        ))}
                                      </div>
                                    </div>
                                  </div>
                                ) : (
                                  <div className="text-xs text-slate-500 flex items-center gap-2 p-2">
                                    <Loader2 className="w-4 h-4 animate-spin" /> {aiService === 'google' ? 'Gemini' : 'GPT'} 분석 중...
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  };

  // 장외 시간 여부
  const isAfterHours = !isMarketHours();

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-black text-white flex items-center gap-3">
            <Sparkles className="w-8 h-8 text-point-cyan" />
            AI 추천
          </h1>
          <p className="text-slate-500 mt-2 font-medium">
            모델 선택 후 "AI 예측"을 누르면 필터2로 예측을 실행합니다.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* 장외 시간 표시 */}
          {isAfterHours && (
            <div className="flex items-center gap-1.5 text-xs text-slate-500 mr-2 bg-slate-800/50 px-2 py-1 rounded-lg">
              <Moon className="w-3 h-3" />
              장외 시간
            </div>
          )}
          
          {/* 스케줄러 상태 표시 */}
          {schedulerStatus && (
            <div className="flex items-center gap-2 text-xs text-slate-500 mr-4">
              {schedulerStatus.crawling_status && (
                <span className="flex items-center gap-1 text-amber-400">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  {schedulerStatus.crawling_status === 'eod' ? 'EOD 수집중' : '장중 수집중'}
                </span>
              )}
              {schedulerStatus.inference_done_today && (
                <span className="flex items-center gap-1 text-emerald-400">
                  <CheckCircle2 className="w-3 h-3" />
                  오늘 분석 완료
                </span>
              )}
            </div>
          )}

          <label className="text-sm text-slate-400 font-semibold">AI 서비스</label>
          <div className="flex rounded-xl overflow-hidden border border-slate-700">
            <button
              onClick={() => setAiService('openai')}
              className={`px-3 py-2 text-xs font-bold transition-all ${
                aiService === 'openai' 
                  ? 'bg-emerald-500 text-white' 
                  : 'bg-[#1a1f2e] text-slate-400 hover:text-white'
              }`}
            >
              GPT
            </button>
            <button
              onClick={() => setAiService('gemini')}
              className={`px-3 py-2 text-xs font-bold transition-all ${
                aiService === 'gemini' 
                  ? 'bg-blue-500 text-white' 
                  : 'bg-[#1a1f2e] text-slate-400 hover:text-white'
              }`}
            >
              Gemini
            </button>
          </div>

          <label className="text-sm text-slate-400 font-semibold">모델 선택</label>
          <select
            value={modelName}
            onChange={(e) => setModelName(e.target.value as ModelName)}
            className="bg-[#1a1f2e] border border-slate-700 text-white text-sm px-3 py-2 rounded-xl focus:outline-none focus:border-point-cyan"
          >
            <option value="model1">모델1 (7-class)</option>
            <option value="model5">모델5 (LightGBM 2%+)</option>
          </select>

          <button
            onClick={() => fetchRecommendations('filter2', true)}
            disabled={isCrawling}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-point-cyan text-white font-bold hover:bg-point-cyan/90 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Zap className="w-4 h-4" />
            AI 예측
          </button>
        </div>
      </div>

      {/* 데이터 수집 패널 */}
      <DataCollectionPanel 
        schedulerStatus={schedulerStatus} 
        onRefreshStatus={fetchSchedulerStatus}
      />

      {/* KIS API 연결 상태 경고 (사용 불가 시에만 표시) */}
      {!kisApiStatus.available && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-2xl p-4 mb-6 animate-in fade-in duration-300">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-amber-500/20 flex items-center justify-center flex-shrink-0">
              <AlertCircle className="w-5 h-5 text-amber-400" />
            </div>
            <div className="flex-1">
              <h4 className="text-amber-400 font-bold text-sm">실시간 시세 조회 불가</h4>
              <p className="text-slate-400 text-xs mt-0.5">
                KIS API 연결에 문제가 있어 실시간 가격 대신 기준가(전일 종가)를 표시합니다.
                {kisApiStatus.error && <span className="text-amber-300 ml-1">({kisApiStatus.error})</span>}
              </p>
            </div>
            <div className="flex-shrink-0">
              <span className="text-xs text-slate-500 bg-slate-800 px-2 py-1 rounded-lg">기준가 표시중</span>
            </div>
          </div>
        </div>
      )}

      {/* 계좌 현황 패널 */}
      <AccountPanel onTotalAssetChange={setTotalAsset} />

      {/* 매수/매도 비율 설정 패널 */}
      <div className="bg-[#1a1f2e] border border-slate-800 rounded-2xl mb-8 overflow-hidden">
        <div 
          className="flex items-center justify-between p-4 cursor-pointer hover:bg-slate-800/30 transition-colors"
          onClick={() => setShowTradeSettings(!showTradeSettings)}
        >
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-violet-500/20 flex items-center justify-center">
              <Settings className="w-5 h-5 text-violet-400" />
            </div>
            <div>
              <h3 className="text-white font-bold">매매 설정</h3>
              <p className="text-xs text-slate-500">
                매수: 총자산의 {buyRatio}% | 매도: 보유의 {sellRatio}%
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {selectedStocks.size > 0 && (
              <span className="text-xs bg-point-cyan/20 text-point-cyan px-2 py-1 rounded-full">
                {selectedStocks.size}종목 선택됨
              </span>
            )}
            <div className="text-slate-400">
              {showTradeSettings ? <ChevronDown className="w-5 h-5" /> : <ChevronRight className="w-5 h-5" />}
            </div>
          </div>
        </div>

        {showTradeSettings && (
          <div className="p-4 pt-0 border-t border-slate-800 animate-in slide-in-from-top-2 duration-200">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              {/* 매수 비율 설정 */}
              <div className="bg-slate-800/50 rounded-xl p-4">
                <div className="flex items-center gap-2 mb-3">
                  <DollarSign className="w-4 h-4 text-point-cyan" />
                  <span className="text-sm font-bold text-white">매수 비율</span>
                </div>
                <p className="text-xs text-slate-400 mb-3">
                  총자산 대비 종목별 매수 금액 비율
                </p>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min="1"
                    max="100"
                    value={buyRatio}
                    onChange={(e) => setBuyRatio(parseInt(e.target.value))}
                    className="flex-1 h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-point-cyan"
                  />
                  <div className="flex items-center gap-1 bg-slate-700 rounded-lg px-2 py-1">
                    <input
                      type="number"
                      min="1"
                      max="100"
                      value={buyRatio}
                      onChange={(e) => setBuyRatio(Math.min(100, Math.max(1, parseInt(e.target.value) || 1)))}
                      className="w-12 bg-transparent text-white text-sm text-right focus:outline-none"
                    />
                    <Percent className="w-3 h-3 text-slate-400" />
                  </div>
                </div>
                {totalAsset > 0 && (
                  <p className="text-xs text-slate-500 mt-2">
                    예상 매수금액: {formatPrice(totalAsset * buyRatio / 100)}원
                  </p>
                )}
              </div>

              {/* 매도 비율 설정 */}
              <div className="bg-slate-800/50 rounded-xl p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Banknote className="w-4 h-4 text-rose-400" />
                  <span className="text-sm font-bold text-white">매도 비율</span>
                </div>
                <p className="text-xs text-slate-400 mb-3">
                  보유수량 대비 분할매도 비율
                </p>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min="1"
                    max="100"
                    value={sellRatio}
                    onChange={(e) => setSellRatio(parseInt(e.target.value))}
                    className="flex-1 h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-rose-400"
                  />
                  <div className="flex items-center gap-1 bg-slate-700 rounded-lg px-2 py-1">
                    <input
                      type="number"
                      min="1"
                      max="100"
                      value={sellRatio}
                      onChange={(e) => setSellRatio(Math.min(100, Math.max(1, parseInt(e.target.value) || 1)))}
                      className="w-12 bg-transparent text-white text-sm text-right focus:outline-none"
                    />
                    <Percent className="w-3 h-3 text-slate-400" />
                  </div>
                </div>
              </div>
            </div>

            {/* 일괄 매수/매도 버튼 */}
            <div className="flex gap-3">
              <button
                onClick={handleBatchBuy}
                disabled={selectedStocks.size === 0 || isBatchOrdering}
                className="flex-1 bg-point-cyan/10 hover:bg-point-cyan text-point-cyan hover:text-white border border-point-cyan/30 py-2.5 rounded-xl font-bold transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isBatchOrdering ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShoppingCart className="w-4 h-4" />}
                선택종목 일괄 매수 ({selectedStocks.size})
              </button>
              <button
                onClick={handleBatchSell}
                disabled={selectedStocks.size === 0 || isBatchOrdering}
                className="flex-1 bg-rose-500/10 hover:bg-rose-500 text-rose-400 hover:text-white border border-rose-500/30 py-2.5 rounded-xl font-bold transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isBatchOrdering ? <Loader2 className="w-4 h-4 animate-spin" /> : <Banknote className="w-4 h-4" />}
                선택종목 일괄 매도 ({selectedStocks.size})
              </button>
            </div>

            {/* 일괄 주문 결과 */}
            {batchOrderResult && (
              <div className="mt-4 p-3 bg-slate-800/50 rounded-lg">
                <p className="text-sm text-white font-bold mb-2">
                  주문 결과: 성공 {batchOrderResult.summary?.success || 0}개 / 실패 {batchOrderResult.summary?.failed || 0}개
                </p>
                <div className="text-xs text-slate-400 max-h-24 overflow-y-auto">
                  {batchOrderResult.results?.map((r: any, idx: number) => (
                    <div key={idx} className={`flex justify-between ${r.success ? 'text-emerald-400' : 'text-rose-400'}`}>
                      <span>{r.code}</span>
                      <span>{r.success ? `주문번호: ${r.orderNo}` : r.error}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="space-y-12">
        {renderSection(
          'filter2',
          `AI 추천 (${modelName === 'model1' ? 'CatBoost' : 'LightGBM'})`,
          'Prob≥70% + 시총≥500억 + Daily≥-5% + return_1d[-5%,29.5%)'
        )}
      </div>
    </div>
  );
};



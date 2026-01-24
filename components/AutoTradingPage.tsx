import React, { useState, useEffect, useCallback } from 'react';
import { 
  Bot, 
  Play, 
  Square, 
  RefreshCw, 
  TrendingUp, 
  TrendingDown,
  AlertCircle,
  CheckCircle2,
  Clock,
  Target,
  DollarSign,
  Activity,
  Zap,
  ShoppingCart,
  Banknote,
  Database,
  Settings,
  ChevronDown,
  ChevronRight,
  Loader2,
  Calendar,
  BarChart2,
  History,
  Eye,
  EyeOff,
  Wallet,
  XCircle
} from 'lucide-react';

// Use relative path for API calls to work with domain/proxy
const API_BASE_URL = '/api';

// 타입 정의
interface Position {
  code: string;
  name: string;
  state: string;
  prev_close: number;
  entry_price: number;
  current_price: number;
  quantity: number;
  unrealized_pnl: number;
  unrealized_pnl_rate: number;
  order_id: string;
  pending_quantity: number;
  gap_confirms: number;
  entry_time: string;
  exit_time: string;
  exit_reason: string;
  error_message: string;
  retry_count: number;
}

interface UniverseStock {
  code: string;
  name: string;
  prev_close: number;
  prev_high: number;
  change_rate: number;
  market_cap: number;
  added_date: string;
}

interface LogEntry {
  timestamp: string;
  level: string;
  event: string;
  code: string;
  message: string;
  data: any;
}

interface StrategyConfig {
  upper_limit_rate: number;
  min_market_cap: number;
  gap_threshold: number;
  gap_confirm_count: number;
  entry_start_time: string;
  entry_end_time: string;
  take_profit_rate: number;
  stop_loss_rate: number;
  eod_sell_start: string;
  eod_sell_end: string;
  max_daily_loss_rate: number;
  max_positions: number;
}

interface TradeHistory {
  id: number;
  trade_date: string;
  code: string;
  name: string;
  trade_type: string;
  quantity: number;
  price: number;
  amount: number;
  exit_reason: string | null;
  pnl: number | null;
  pnl_rate: number | null;
  created_at: string;
}

interface StrategyStatus {
  is_running: boolean;
  phase: string;
  today: string;
  total_asset: number;
  available_cash: number;
  daily_pnl: number;
  daily_pnl_rate: number;
  universe: UniverseStock[];
  positions: Record<string, Position>;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  logs: LogEntry[];
  last_update: string;
  // 모드 정보
  mode?: 'mock' | 'real';
  label?: string;
  is_mock?: boolean;
}

// 포맷 함수
const formatPrice = (price: number) => {
  return new Intl.NumberFormat('ko-KR').format(price);
};

const formatPercent = (rate: number) => {
  return `${rate >= 0 ? '+' : ''}${rate.toFixed(2)}%`;
};

const formatTime = (isoString: string) => {
  if (!isoString) return '-';
  const date = new Date(isoString);
  return date.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
};

// 상태 뱃지 컴포넌트
const StateBadge: React.FC<{ state: string }> = ({ state }) => {
  const stateConfig: Record<string, { bg: string; text: string; label: string }> = {
    IDLE: { bg: 'bg-slate-500/20', text: 'text-slate-400', label: '대기' },
    WATCHING: { bg: 'bg-amber-500/20', text: 'text-amber-400', label: '감시중' },
    ENTRY_PENDING: { bg: 'bg-blue-500/20', text: 'text-blue-400', label: '진입대기' },
    ENTERED: { bg: 'bg-emerald-500/20', text: 'text-emerald-400', label: '보유중' },
    EXIT_PENDING: { bg: 'bg-violet-500/20', text: 'text-violet-400', label: '청산대기' },
    CLOSED: { bg: 'bg-slate-500/20', text: 'text-slate-400', label: '청산완료' },
    SKIPPED: { bg: 'bg-rose-500/20', text: 'text-rose-400', label: '건너뜀' },
    ERROR: { bg: 'bg-rose-500/20', text: 'text-rose-400', label: '오류' }
  };

  const config = stateConfig[state] || stateConfig.IDLE;

  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${config.bg} ${config.text}`}>
      {config.label}
    </span>
  );
};

// 단계 뱃지 컴포넌트
const PhaseBadge: React.FC<{ phase: string }> = ({ phase }) => {
  const phaseConfig: Record<string, { bg: string; text: string; label: string; icon: React.ReactNode }> = {
    IDLE: { bg: 'bg-slate-600', text: 'text-slate-200', label: '비활성', icon: <Clock className="w-4 h-4" /> },
    PREPARING: { bg: 'bg-amber-600', text: 'text-white', label: '준비중', icon: <Settings className="w-4 h-4 animate-spin" /> },
    ENTRY_WINDOW: { bg: 'bg-emerald-600', text: 'text-white', label: '진입구간', icon: <Zap className="w-4 h-4 animate-pulse" /> },
    MONITORING: { bg: 'bg-blue-600', text: 'text-white', label: '모니터링', icon: <Activity className="w-4 h-4" /> },
    EOD_CLOSING: { bg: 'bg-violet-600', text: 'text-white', label: 'EOD청산', icon: <TrendingDown className="w-4 h-4" /> },
    CLOSED: { bg: 'bg-slate-600', text: 'text-slate-200', label: '장종료', icon: <CheckCircle2 className="w-4 h-4" /> }
  };

  const config = phaseConfig[phase] || phaseConfig.IDLE;

  return (
    <span className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-bold ${config.bg} ${config.text}`}>
      {config.icon}
      {config.label}
    </span>
  );
};

export const AutoTradingPage: React.FC = () => {
  const [status, setStatus] = useState<StrategyStatus | null>(null);
  const [config, setConfig] = useState<StrategyConfig | null>(null);
  const [tradeHistory, setTradeHistory] = useState<TradeHistory[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // UI 상태
  const [showLogs, setShowLogs] = useState(false);
  const [showConfig, setShowConfig] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  
  // 수동 주문
  const [manualCode, setManualCode] = useState('');
  const [manualQuantity, setManualQuantity] = useState('');
  const [isOrdering, setIsOrdering] = useState(false);
  
  // 설정 수정
  const [editMaxPositions, setEditMaxPositions] = useState('5');
  const [editTakeProfit, setEditTakeProfit] = useState('10');
  const [editStopLoss, setEditStopLoss] = useState('-3');
  const [isUpdatingConfig, setIsUpdatingConfig] = useState(false);
  
  // 모드 전환
  const [isSwitchingMode, setIsSwitchingMode] = useState(false);
  const [isTradingDay, setIsTradingDay] = useState<boolean | null>(null);

  // 상태 조회
  const fetchStatus = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/auto-trading/status`);
      const data = await response.json();
      if (data.success) {
        setStatus(data);
        setError(null);
      } else {
        setError(data.error || '상태 조회 실패');
      }
    } catch (err) {
      setError('서버 연결 실패');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // 설정 조회
  const fetchConfig = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/auto-trading/config`);
      const data = await response.json();
      if (data.success) {
        setConfig(data.config);
        // 초기값 설정
        setEditMaxPositions(String(data.config.max_positions || 5));
        setEditTakeProfit(String(data.config.take_profit_rate || 10));
        setEditStopLoss(String(data.config.stop_loss_rate || -3));
      }
    } catch (err) {
      console.error('설정 조회 실패:', err);
    }
  }, []);
  
  // 설정 업데이트
  const handleUpdateConfig = async () => {
    setIsUpdatingConfig(true);
    try {
      const response = await fetch(`${API_BASE_URL}/auto-trading/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          max_positions: parseInt(editMaxPositions),
          take_profit_rate: parseFloat(editTakeProfit),
          stop_loss_rate: parseFloat(editStopLoss)
        })
      });
      const data = await response.json();
      if (data.success) {
        alert('설정이 업데이트되었습니다.');
        fetchConfig();
      } else {
        alert(data.error || '설정 업데이트 실패');
      }
    } catch (err) {
      alert('서버 연결 실패');
    } finally {
      setIsUpdatingConfig(false);
    }
  };

  // 거래 내역 조회
  const fetchTradeHistory = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/auto-trading/trade-history?days=7`);
      const data = await response.json();
      if (data.success) {
        setTradeHistory(data.history || []);
      }
    } catch (err) {
      console.error('거래 내역 조회 실패:', err);
    }
  }, []);

  // 거래일 확인
  const fetchTradingDayStatus = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/auto-trading/is-trading-day`);
      const data = await response.json();
      if (data.success) {
        setIsTradingDay(data.is_trading_day);
      }
    } catch (err) {
      console.error('거래일 확인 실패:', err);
    }
  }, []);

  // 모드 전환
  const handleModeSwitch = async (newMode: 'mock' | 'real') => {
    if (status?.is_running) {
      alert('자동매매가 실행 중입니다. 먼저 중지해주세요.');
      return;
    }
    
    const modeLabel = newMode === 'mock' ? '모의투자' : '실전투자';
    if (newMode === 'real') {
      if (!window.confirm(`⚠️ 실전투자 모드로 전환하시겠습니까?\n\n실제 계좌에서 주문이 체결됩니다.\n신중하게 결정해주세요.`)) {
        return;
      }
    } else {
      if (!window.confirm(`${modeLabel} 모드로 전환하시겠습니까?`)) {
        return;
      }
    }
    
    setIsSwitchingMode(true);
    try {
      const response = await fetch(`${API_BASE_URL}/auto-trading/mode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: newMode })
      });
      const data = await response.json();
      if (data.success) {
        alert(`${modeLabel} 모드로 전환되었습니다.`);
        fetchStatus();
      } else {
        alert(data.error || '모드 전환 실패');
      }
    } catch (err) {
      alert('서버 연결 실패');
    } finally {
      setIsSwitchingMode(false);
    }
  };

  // 자동매매 시작
  const handleStart = async () => {
    // 휴장일 체크
    if (isTradingDay === false) {
      if (!window.confirm('오늘은 휴장일입니다. 그래도 시작하시겠습니까?')) {
        return;
      }
    }
    
    try {
      const response = await fetch(`${API_BASE_URL}/auto-trading/start`, { method: 'POST' });
      const data = await response.json();
      if (data.success) {
        fetchStatus();
      } else {
        alert(data.error || '시작 실패');
      }
    } catch (err) {
      alert('서버 연결 실패');
    }
  };

  // 자동매매 중지
  const handleStop = async () => {
    if (!window.confirm('자동매매를 중지하시겠습니까?')) return;
    
    try {
      const response = await fetch(`${API_BASE_URL}/auto-trading/stop`, { method: 'POST' });
      const data = await response.json();
      if (data.success) {
        fetchStatus();
      } else {
        alert(data.error || '중지 실패');
      }
    } catch (err) {
      alert('서버 연결 실패');
    }
  };

  // 유니버스 구축
  const handleBuildUniverse = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/auto-trading/build-universe`, { method: 'POST' });
      const data = await response.json();
      if (data.success) {
        if (data.count > 0) {
          alert(`유니버스 구축 완료: ${data.count}개 종목`);
        } else {
          alert('유니버스 구축 완료: 전일 상한가 종목이 없습니다.');
        }
        fetchStatus();
      } else {
        alert(data.error || '유니버스 구축 실패');
      }
    } catch (err) {
      alert('서버 연결 실패');
    }
  };

  // 포지션 동기화
  const handleRefreshPositions = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/auto-trading/refresh-positions`, { method: 'POST' });
      const data = await response.json();
      if (data.success) {
        fetchStatus();
      } else {
        alert(data.error || '동기화 실패');
      }
    } catch (err) {
      alert('서버 연결 실패');
    }
  };

  // 수동 매수
  const handleManualBuy = async () => {
    if (!manualCode || !manualQuantity) {
      alert('종목코드와 수량을 입력하세요');
      return;
    }
    
    setIsOrdering(true);
    try {
      const response = await fetch(`${API_BASE_URL}/auto-trading/manual-buy`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: manualCode, quantity: parseInt(manualQuantity) })
      });
      const data = await response.json();
      if (data.success) {
        alert(`매수 주문 완료: ${data.order_no}`);
        setManualCode('');
        setManualQuantity('');
        fetchStatus();
      } else {
        alert(data.error || '매수 실패');
      }
    } catch (err) {
      alert('서버 연결 실패');
    } finally {
      setIsOrdering(false);
    }
  };

  // 수동 매도
  const handleManualSell = async (code: string, quantity: number = 0) => {
    if (!window.confirm(`${code} 종목을 ${quantity > 0 ? quantity + '주' : '전량'} 매도하시겠습니까?`)) return;
    
    try {
      const response = await fetch(`${API_BASE_URL}/auto-trading/manual-sell`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, quantity })
      });
      const data = await response.json();
      if (data.success) {
        alert(`매도 주문 완료: ${data.order_no}`);
        fetchStatus();
      } else {
        alert(data.error || '매도 실패');
      }
    } catch (err) {
      alert('서버 연결 실패');
    }
  };

  // 초기 로드 및 주기적 갱신
  useEffect(() => {
    fetchStatus();
    fetchConfig();
    fetchTradeHistory();
    fetchTradingDayStatus();
    
    const interval = setInterval(fetchStatus, 3000); // 3초마다 갱신
    return () => clearInterval(interval);
  }, [fetchStatus, fetchConfig, fetchTradeHistory, fetchTradingDayStatus]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-12 h-12 text-point-cyan animate-spin" />
          <p className="text-slate-400">자동매매 상태 로딩 중...</p>
        </div>
      </div>
    );
  }

  const activePositions = status ? Object.values(status.positions).filter(p => p.state === 'ENTERED') : [];
  const watchingPositions = status ? Object.values(status.positions).filter(p => p.state === 'WATCHING') : [];
  const pendingPositions = status ? Object.values(status.positions).filter(p => p.state.includes('PENDING')) : [];

  return (
    <div className="p-4 md:p-8 max-w-7xl mx-auto">
      {/* 헤더 */}
      <div className="flex flex-col md:flex-row md:items-center justify-between mb-6 md:mb-8 gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-black text-white flex items-center gap-3">
            <Bot className="w-7 h-7 md:w-8 md:h-8 text-point-cyan" />
            자동매매
          </h1>
          <p className="text-slate-500 mt-1 md:mt-2 text-sm md:text-base font-medium">
            전략 1: 상한가 갭상승 모멘텀 (TP: +10%, SL: -3%)
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 md:gap-3">
          {/* 휴장일 표시 */}
          {isTradingDay === false && (
            <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-bold bg-amber-500/20 text-amber-400">
              <Calendar className="w-4 h-4" />
              휴장일
            </span>
          )}
          
          {status && <PhaseBadge phase={status.phase} />}
          
          {/* 모드 전환 버튼 */}
          <div className="flex rounded-xl overflow-hidden border border-slate-700">
            <button
              onClick={() => handleModeSwitch('mock')}
              disabled={isSwitchingMode || status?.mode === 'mock'}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-sm font-bold transition-all ${
                status?.mode === 'mock' || status?.is_mock
                  ? 'bg-emerald-500/20 text-emerald-400'
                  : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
              }`}
            >
              🟢 모의
            </button>
            <button
              onClick={() => handleModeSwitch('real')}
              disabled={isSwitchingMode || status?.mode === 'real'}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-sm font-bold transition-all ${
                status?.mode === 'real' || (status?.is_mock === false)
                  ? 'bg-rose-500/20 text-rose-400 animate-pulse'
                  : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
              }`}
            >
              🔴 실전
            </button>
          </div>
          
          {status?.is_running ? (
            <button
              onClick={handleStop}
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-rose-500 text-white font-bold hover:bg-rose-600 transition-all"
            >
              <Square className="w-4 h-4" />
              중지
            </button>
          ) : (
            <button
              onClick={handleStart}
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-500 text-white font-bold hover:bg-emerald-600 transition-all"
            >
              <Play className="w-4 h-4" />
              시작
            </button>
          )}
          
          <button
            onClick={fetchStatus}
            className="p-2 rounded-xl bg-slate-700 text-white hover:bg-slate-600 transition-all"
            title="새로고침"
          >
            <RefreshCw className="w-5 h-5" />
          </button>
        </div>
      </div>
      
      {/* 실전투자 경고 */}
      {status?.mode === 'real' && (
        <div className="bg-rose-500/10 border border-rose-500/30 rounded-2xl p-4 mb-6 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-rose-400 flex-shrink-0 animate-pulse" />
          <p className="text-rose-400 text-sm font-bold">
            ⚠️ 실전투자 모드입니다. 실제 계좌에서 주문이 체결됩니다.
          </p>
        </div>
      )}

      {/* 에러 메시지 */}
      {error && (
        <div className="bg-rose-500/10 border border-rose-500/30 rounded-2xl p-4 mb-6 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-rose-400 flex-shrink-0" />
          <p className="text-rose-400 text-sm">{error}</p>
        </div>
      )}

      {/* 통계 카드 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4 mb-6">
        <div className="bg-[#1a1f2e] border border-slate-800 rounded-2xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <Wallet className="w-4 h-4 text-point-cyan" />
            <span className="text-xs text-slate-500">총 자산</span>
          </div>
          <p className="text-lg md:text-xl font-bold text-white">
            {formatPrice(status?.total_asset || 0)}원
          </p>
        </div>
        
        <div className="bg-[#1a1f2e] border border-slate-800 rounded-2xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <DollarSign className="w-4 h-4 text-emerald-400" />
            <span className="text-xs text-slate-500">가용 현금</span>
          </div>
          <p className="text-lg md:text-xl font-bold text-white">
            {formatPrice(status?.available_cash || 0)}원
          </p>
        </div>
        
        <div className="bg-[#1a1f2e] border border-slate-800 rounded-2xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="w-4 h-4 text-violet-400" />
            <span className="text-xs text-slate-500">금일 손익</span>
          </div>
          <p className={`text-lg md:text-xl font-bold ${(status?.daily_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {formatPrice(status?.daily_pnl || 0)}원
          </p>
        </div>
        
        <div className="bg-[#1a1f2e] border border-slate-800 rounded-2xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <Target className="w-4 h-4 text-amber-400" />
            <span className="text-xs text-slate-500">승률</span>
          </div>
          <p className="text-lg md:text-xl font-bold text-white">
            {status && status.total_trades > 0 
              ? `${((status.winning_trades / status.total_trades) * 100).toFixed(1)}%`
              : '-'}
          </p>
          <p className="text-xs text-slate-500">
            {status?.winning_trades || 0}승 / {status?.losing_trades || 0}패
          </p>
        </div>
      </div>

      {/* 액션 버튼 */}
      <div className="flex flex-wrap gap-2 mb-6">
        <button
          onClick={handleBuildUniverse}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-400 hover:bg-amber-500/20 transition-all text-sm font-bold"
        >
          <Database className="w-4 h-4" />
          유니버스 구축
        </button>
        
        <button
          onClick={handleRefreshPositions}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-500/10 border border-blue-500/30 text-blue-400 hover:bg-blue-500/20 transition-all text-sm font-bold"
        >
          <RefreshCw className="w-4 h-4" />
          포지션 동기화
        </button>
        
        <button
          onClick={() => setShowConfig(!showConfig)}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-500/10 border border-slate-500/30 text-slate-400 hover:bg-slate-500/20 transition-all text-sm font-bold"
        >
          <Settings className="w-4 h-4" />
          전략 설정
        </button>
        
        <button
          onClick={() => { setShowHistory(!showHistory); if (!showHistory) fetchTradeHistory(); }}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-violet-500/10 border border-violet-500/30 text-violet-400 hover:bg-violet-500/20 transition-all text-sm font-bold"
        >
          <History className="w-4 h-4" />
          거래 내역
        </button>
        
        <button
          onClick={() => setShowLogs(!showLogs)}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-500/10 border border-slate-500/30 text-slate-400 hover:bg-slate-500/20 transition-all text-sm font-bold"
        >
          {showLogs ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          로그
        </button>
      </div>

      {/* 전략 설정 패널 */}
      {showConfig && config && (
        <div className="bg-[#1a1f2e] border border-slate-800 rounded-2xl p-4 mb-6 animate-in slide-in-from-top-2 duration-200">
          <h3 className="text-white font-bold mb-4 flex items-center gap-2">
            <Settings className="w-5 h-5 text-point-cyan" />
            전략 설정
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <span className="text-slate-500">상한가 기준</span>
              <p className="text-white font-bold">{config.upper_limit_rate}%</p>
            </div>
            <div>
              <span className="text-slate-500">최소 시총</span>
              <p className="text-white font-bold">{config.min_market_cap}억</p>
            </div>
            <div>
              <span className="text-slate-500">갭 기준</span>
              <p className="text-white font-bold">+{config.gap_threshold}%</p>
            </div>
            <div>
              <span className="text-slate-500">갭 확인</span>
              <p className="text-white font-bold">{config.gap_confirm_count}회</p>
            </div>
            <div>
              <span className="text-slate-500">익절</span>
              <p className="text-emerald-400 font-bold">+{config.take_profit_rate}%</p>
            </div>
            <div>
              <span className="text-slate-500">손절</span>
              <p className="text-rose-400 font-bold">{config.stop_loss_rate}%</p>
            </div>
            <div>
              <span className="text-slate-500">최대 포지션</span>
              <p className="text-white font-bold">{config.max_positions}개</p>
            </div>
            <div>
              <span className="text-slate-500">종목당 투자비율</span>
              <p className="text-point-cyan font-bold">1/{config.max_positions} (= {(100 / config.max_positions).toFixed(1)}%)</p>
            </div>
          </div>
          
          {/* 설정 수정 폼 */}
          <div className="mt-4 pt-4 border-t border-slate-700">
            <h4 className="text-sm text-slate-400 mb-3">설정 변경</h4>
            <div className="flex flex-wrap items-end gap-3">
              <div className="min-w-[100px]">
                <label className="text-xs text-slate-500 mb-1 block">최대 포지션</label>
                <input
                  type="number"
                  value={editMaxPositions}
                  onChange={(e) => setEditMaxPositions(e.target.value)}
                  min="1"
                  max="10"
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-point-cyan"
                />
              </div>
              <div className="min-w-[100px]">
                <label className="text-xs text-slate-500 mb-1 block">익절 (%)</label>
                <input
                  type="number"
                  value={editTakeProfit}
                  onChange={(e) => setEditTakeProfit(e.target.value)}
                  step="0.5"
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-point-cyan"
                />
              </div>
              <div className="min-w-[100px]">
                <label className="text-xs text-slate-500 mb-1 block">손절 (%)</label>
                <input
                  type="number"
                  value={editStopLoss}
                  onChange={(e) => setEditStopLoss(e.target.value)}
                  step="0.5"
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-point-cyan"
                />
              </div>
              <button
                onClick={handleUpdateConfig}
                disabled={isUpdatingConfig}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-point-cyan text-white font-bold hover:bg-point-cyan/90 transition-all disabled:opacity-50"
              >
                {isUpdatingConfig ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                적용
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 거래 내역 패널 */}
      {showHistory && (
        <div className="bg-[#1a1f2e] border border-slate-800 rounded-2xl p-4 mb-6 animate-in slide-in-from-top-2 duration-200">
          <h3 className="text-white font-bold mb-4 flex items-center gap-2">
            <History className="w-5 h-5 text-violet-400" />
            최근 7일 거래 내역
          </h3>
          {tradeHistory.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-slate-500 border-b border-slate-800">
                    <th className="text-left py-2 px-2">날짜</th>
                    <th className="text-left py-2 px-2">종목</th>
                    <th className="text-left py-2 px-2">구분</th>
                    <th className="text-right py-2 px-2">수량</th>
                    <th className="text-right py-2 px-2">가격</th>
                    <th className="text-right py-2 px-2">손익</th>
                    <th className="text-left py-2 px-2">사유</th>
                  </tr>
                </thead>
                <tbody>
                  {tradeHistory.map((trade) => (
                    <tr key={trade.id} className="border-b border-slate-800/50">
                      <td className="py-2 px-2 text-slate-400">{trade.trade_date}</td>
                      <td className="py-2 px-2 text-white">{trade.name}</td>
                      <td className="py-2 px-2">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                          trade.trade_type === 'buy' 
                            ? 'bg-emerald-500/20 text-emerald-400' 
                            : 'bg-rose-500/20 text-rose-400'
                        }`}>
                          {trade.trade_type === 'buy' ? '매수' : '매도'}
                        </span>
                      </td>
                      <td className="py-2 px-2 text-right text-white">{trade.quantity}</td>
                      <td className="py-2 px-2 text-right text-white">{formatPrice(trade.price)}</td>
                      <td className={`py-2 px-2 text-right font-bold ${
                        (trade.pnl || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                      }`}>
                        {trade.pnl !== null ? `${formatPrice(trade.pnl)} (${formatPercent(trade.pnl_rate || 0)})` : '-'}
                      </td>
                      <td className="py-2 px-2 text-slate-400">{trade.exit_reason || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-slate-500 text-center py-4">거래 내역이 없습니다.</p>
          )}
        </div>
      )}

      {/* 보유 포지션 */}
      <div className="bg-[#1a1f2e] border border-slate-800 rounded-2xl mb-6 overflow-hidden">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <h3 className="text-white font-bold flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-emerald-400" />
            보유 포지션 ({activePositions.length})
          </h3>
        </div>
        
        {activePositions.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-500 border-b border-slate-800 bg-slate-800/30">
                  <th className="text-left py-3 px-4">종목</th>
                  <th className="text-left py-3 px-4">상태</th>
                  <th className="text-right py-3 px-4">수량</th>
                  <th className="text-right py-3 px-4">진입가</th>
                  <th className="text-right py-3 px-4">현재가</th>
                  <th className="text-right py-3 px-4">손익</th>
                  <th className="text-center py-3 px-4">액션</th>
                </tr>
              </thead>
              <tbody>
                {activePositions.map((pos) => (
                  <tr key={pos.code} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                    <td className="py-3 px-4">
                      <div className="font-bold text-white">{pos.name || pos.code}</div>
                      <div className="text-xs text-slate-500">{pos.code}</div>
                    </td>
                    <td className="py-3 px-4"><StateBadge state={pos.state} /></td>
                    <td className="py-3 px-4 text-right text-white">{pos.quantity}주</td>
                    <td className="py-3 px-4 text-right text-slate-400">{formatPrice(pos.entry_price)}원</td>
                    <td className="py-3 px-4 text-right text-white">{formatPrice(pos.current_price)}원</td>
                    <td className={`py-3 px-4 text-right font-bold ${pos.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {formatPrice(pos.unrealized_pnl)}원
                      <div className="text-xs">{formatPercent(pos.unrealized_pnl_rate)}</div>
                    </td>
                    <td className="py-3 px-4 text-center">
                      <button
                        onClick={() => handleManualSell(pos.code)}
                        className="bg-rose-500/10 hover:bg-rose-500 text-rose-400 hover:text-white border border-rose-500/30 px-3 py-1 rounded-lg text-xs font-bold transition-all"
                      >
                        전량매도
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-8 text-center text-slate-500">
            보유 중인 포지션이 없습니다.
          </div>
        )}
      </div>

      {/* 감시 종목 (유니버스) */}
      <div className="bg-[#1a1f2e] border border-slate-800 rounded-2xl mb-6 overflow-hidden">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <h3 className="text-white font-bold flex items-center gap-2">
            <Eye className="w-5 h-5 text-amber-400" />
            감시 종목 ({watchingPositions.length})
          </h3>
        </div>
        
        {watchingPositions.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-500 border-b border-slate-800 bg-slate-800/30">
                  <th className="text-left py-3 px-4">종목</th>
                  <th className="text-left py-3 px-4">상태</th>
                  <th className="text-right py-3 px-4">전일 종가</th>
                  <th className="text-right py-3 px-4">현재가</th>
                  <th className="text-right py-3 px-4">갭 확인</th>
                  <th className="text-center py-3 px-4">액션</th>
                </tr>
              </thead>
              <tbody>
                {watchingPositions.map((pos) => {
                  const gapRate = pos.prev_close > 0 && pos.current_price > 0
                    ? ((pos.current_price - pos.prev_close) / pos.prev_close * 100)
                    : 0;
                  
                  return (
                    <tr key={pos.code} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                      <td className="py-3 px-4">
                        <div className="font-bold text-white">{pos.name || pos.code}</div>
                        <div className="text-xs text-slate-500">{pos.code}</div>
                      </td>
                      <td className="py-3 px-4"><StateBadge state={pos.state} /></td>
                      <td className="py-3 px-4 text-right text-slate-400">{formatPrice(pos.prev_close)}원</td>
                      <td className="py-3 px-4 text-right text-white">
                        {pos.current_price > 0 ? `${formatPrice(pos.current_price)}원` : '-'}
                        {gapRate !== 0 && (
                          <div className={`text-xs ${gapRate >= 2 ? 'text-emerald-400' : 'text-slate-500'}`}>
                            갭 {formatPercent(gapRate)}
                          </div>
                        )}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <span className={`font-bold ${pos.gap_confirms > 0 ? 'text-emerald-400' : 'text-slate-500'}`}>
                          {pos.gap_confirms}/{config?.gap_confirm_count || 2}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-center">
                        <button
                          onClick={() => {
                            setManualCode(pos.code);
                            setManualQuantity('1');
                          }}
                          className="bg-point-cyan/10 hover:bg-point-cyan text-point-cyan hover:text-white border border-point-cyan/30 px-3 py-1 rounded-lg text-xs font-bold transition-all"
                        >
                          수동매수
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-8 text-center text-slate-500">
            감시 중인 종목이 없습니다. "유니버스 구축" 버튼을 눌러 종목을 추가하세요.
          </div>
        )}
      </div>

      {/* 수동 주문 패널 */}
      <div className="bg-[#1a1f2e] border border-slate-800 rounded-2xl p-4 mb-6">
        <h3 className="text-white font-bold mb-4 flex items-center gap-2">
          <ShoppingCart className="w-5 h-5 text-point-cyan" />
          수동 주문
        </h3>
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[120px]">
            <label className="text-xs text-slate-500 mb-1 block">종목코드</label>
            <input
              type="text"
              value={manualCode}
              onChange={(e) => setManualCode(e.target.value)}
              placeholder="005930"
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-point-cyan"
            />
          </div>
          <div className="flex-1 min-w-[100px]">
            <label className="text-xs text-slate-500 mb-1 block">수량</label>
            <input
              type="number"
              value={manualQuantity}
              onChange={(e) => setManualQuantity(e.target.value)}
              placeholder="1"
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-point-cyan"
            />
          </div>
          <button
            onClick={handleManualBuy}
            disabled={isOrdering}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-point-cyan text-white font-bold hover:bg-point-cyan/90 transition-all disabled:opacity-50"
          >
            {isOrdering ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShoppingCart className="w-4 h-4" />}
            매수
          </button>
        </div>
      </div>

      {/* 로그 패널 */}
      {showLogs && (
        <div className="bg-[#1a1f2e] border border-slate-800 rounded-2xl p-4 animate-in slide-in-from-top-2 duration-200">
          <h3 className="text-white font-bold mb-4 flex items-center gap-2">
            <Activity className="w-5 h-5 text-slate-400" />
            실시간 로그
          </h3>
          <div className="bg-slate-900 rounded-lg p-3 max-h-80 overflow-y-auto text-xs font-mono">
            {status?.logs && status.logs.length > 0 ? (
              [...status.logs].reverse().map((log, idx) => (
                <div key={idx} className={`py-1 border-b border-slate-800/50 ${
                  log.level === 'ERROR' ? 'text-rose-400' :
                  log.level === 'WARNING' ? 'text-amber-400' : 'text-slate-400'
                }`}>
                  <span className="text-slate-600">{formatTime(log.timestamp)}</span>
                  {' '}
                  <span className={`px-1 rounded ${
                    log.level === 'ERROR' ? 'bg-rose-500/20' :
                    log.level === 'WARNING' ? 'bg-amber-500/20' : 'bg-slate-700'
                  }`}>{log.event}</span>
                  {' '}
                  {log.code && <span className="text-point-cyan">[{log.code}]</span>}
                  {' '}
                  {log.message}
                </div>
              ))
            ) : (
              <p className="text-slate-500">로그가 없습니다.</p>
            )}
          </div>
        </div>
      )}

      {/* 마지막 업데이트 */}
      {status?.last_update && (
        <div className="text-center text-xs text-slate-600 mt-4">
          마지막 업데이트: {new Date(status.last_update).toLocaleString('ko-KR')}
        </div>
      )}
    </div>
  );
};

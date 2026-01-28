import React, { useState, useEffect, useCallback } from 'react';
import { 
  Bot, 
  Play, 
  Square, 
  RefreshCw, 
  TrendingUp, 
  TrendingDown,
  AlertCircle,
  AlertTriangle,
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
  XCircle,
  Power,
  ToggleLeft,
  ToggleRight,
  CircleDot,
  Wifi,
  WifiOff,
  PlusCircle,
  Trash2,
  X,
  Save
} from 'lucide-react';
import { 
  AutoTradingStock, 
  TradingStrategyConfig, 
  BuyTimeConfig, 
  SellCondition,
  DEFAULT_TRADING_STRATEGY 
} from '../types';
import { loadStockList, searchStocks } from '../services/stockService';

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

interface HeartbeatStatus {
  is_running: boolean;
  is_responsive: boolean;
  last_update: string;
  phase: string;
  thread_alive: boolean;
}

interface AutoTradingSettings {
  auto_start_enabled: boolean;
  auto_start_mode: 'auto' | 'manual';
}

// 포맷 함수
const formatPrice = (price: number) => {
  return new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 0 }).format(Math.floor(price));
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
  const stateConfig: Record<string, { bg: string; text: string; label: string; description: string }> = {
    IDLE: { bg: 'bg-slate-500/20', text: 'text-slate-400', label: '대기', description: '초기 상태' },
    WATCHING: { bg: 'bg-amber-500/20', text: 'text-amber-400', label: '감시중', description: '갭+2% 조건 충족, 진입 감시 중' },
    ENTRY_PENDING: { bg: 'bg-blue-500/20', text: 'text-blue-400', label: '진입대기', description: '매수 주문 체결 대기' },
    ENTERED: { bg: 'bg-emerald-500/20', text: 'text-emerald-400', label: '보유중', description: '포지션 진입 완료' },
    EXIT_PENDING: { bg: 'bg-violet-500/20', text: 'text-violet-400', label: '청산대기', description: '매도 주문 체결 대기' },
    CLOSED: { bg: 'bg-slate-500/20', text: 'text-slate-400', label: '청산완료', description: '청산 완료' },
    SKIPPED: { bg: 'bg-rose-500/20', text: 'text-rose-400', label: '건너뜀', description: '진입 조건 미달로 건너뜀' },
    DISQUALIFIED: { bg: 'bg-gray-500/20', text: 'text-gray-400', label: '탈락', description: '갭+2% 미충족으로 감시 제외' },
    ERROR: { bg: 'bg-rose-500/20', text: 'text-rose-400', label: '오류', description: '오류 발생' }
  };

  const config = stateConfig[state] || stateConfig.IDLE;

  return (
    <span 
      className={`px-2 py-0.5 rounded-full text-xs font-bold ${config.bg} ${config.text}`}
      title={config.description}
    >
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

// Props 타입
interface AutoTradingPageProps {
  initialStocks?: AutoTradingStock[];
  onStocksChange?: (stocks: AutoTradingStock[]) => void;
}

// 로컬스토리지 키 (전략 설정만 로컬에 저장)
const TRADING_STRATEGY_KEY = 'trading_strategy_config';

// 서버에서 자동매매 대상 종목 로드
const fetchTargetStocksFromServer = async (): Promise<AutoTradingStock[]> => {
  try {
    const response = await fetch('/api/auto-trading/target-stocks');
    if (response.ok) {
      const data = await response.json();
      return data.stocks || [];
    }
  } catch (e) {
    console.error('자동매매 대상 종목 로드 실패:', e);
  }
  return [];
};

// 서버에 자동매매 대상 종목 저장
const saveTargetStocksToServer = async (stocks: AutoTradingStock[]): Promise<boolean> => {
  try {
    const response = await fetch('/api/auto-trading/target-stocks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stocks }),
    });
    return response.ok;
  } catch (e) {
    console.error('자동매매 대상 종목 저장 실패:', e);
    return false;
  }
};

// 서버에서 자동매매 대상 종목 삭제
const deleteTargetStocksFromServer = async (codes: string[]): Promise<boolean> => {
  try {
    const response = await fetch('/api/auto-trading/target-stocks', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ codes }),
    });
    return response.ok;
  } catch (e) {
    console.error('자동매매 대상 종목 삭제 실패:', e);
    return false;
  }
};

// 서버에서 자동매매 대상 종목 전체 삭제
const clearTargetStocksFromServer = async (): Promise<boolean> => {
  try {
    const response = await fetch('/api/auto-trading/target-stocks/clear', {
      method: 'DELETE',
    });
    return response.ok;
  } catch (e) {
    console.error('자동매매 대상 종목 전체 삭제 실패:', e);
    return false;
  }
};

// 전략 설정 로드 (로컬 저장 유지)
const loadTradingStrategy = (): TradingStrategyConfig => {
  try {
    const saved = localStorage.getItem(TRADING_STRATEGY_KEY);
    return saved ? JSON.parse(saved) : DEFAULT_TRADING_STRATEGY;
  } catch {
    return DEFAULT_TRADING_STRATEGY;
  }
};

// 전략 설정 저장 (로컬 저장 유지)
const saveTradingStrategy = (config: TradingStrategyConfig) => {
  localStorage.setItem(TRADING_STRATEGY_KEY, JSON.stringify(config));
};

export const AutoTradingPage: React.FC<AutoTradingPageProps> = ({ initialStocks, onStocksChange }) => {
  const [status, setStatus] = useState<StrategyStatus | null>(null);
  const [config, setConfig] = useState<StrategyConfig | null>(null);
  const [tradeHistory, setTradeHistory] = useState<TradeHistory[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Heartbeat 상태 (엔진 실행 여부 신뢰성 확인)
  const [heartbeat, setHeartbeat] = useState<HeartbeatStatus | null>(null);
  
  // 서버 저장 설정
  const [serverSettings, setServerSettings] = useState<AutoTradingSettings>({
    auto_start_enabled: false,
    auto_start_mode: 'manual'
  });
  const [isLoadingSettings, setIsLoadingSettings] = useState(false);
  
  // UI 상태
  const [showLogs, setShowLogs] = useState(false);
  const [showConfig, setShowConfig] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [showStrategySettings, setShowStrategySettings] = useState(false);
  const [showAddStock, setShowAddStock] = useState(false);
  
  // 자동매매 대상 종목 (서버에서 로드)
  const [tradingStocks, setTradingStocks] = useState<AutoTradingStock[]>([]);
  const [isLoadingStocks, setIsLoadingStocks] = useState(true);
  
  // 전략 설정 (로컬스토리지)
  const [strategyConfig, setStrategyConfig] = useState<TradingStrategyConfig>(loadTradingStrategy);
  
  // 수동 종목 추가 입력
  const [newStockCode, setNewStockCode] = useState('');
  const [isSearchingStock, setIsSearchingStock] = useState(false);
  const [stockSearchResults, setStockSearchResults] = useState<{ code: string; name: string }[]>([]);
  const [showSearchResults, setShowSearchResults] = useState(false);
  
  // 수동 주문
  const [manualCode, setManualCode] = useState('');
  const [manualQuantity, setManualQuantity] = useState('');
  const [useAutoQuantity, setUseAutoQuantity] = useState(true);  // 기본값: 1/N 자동 계산
  const [isOrdering, setIsOrdering] = useState(false);
  
  // 설정 수정
  const [editMaxPositions, setEditMaxPositions] = useState('5');
  const [editTakeProfit, setEditTakeProfit] = useState('10');
  const [editStopLoss, setEditStopLoss] = useState('-3');
  const [isUpdatingConfig, setIsUpdatingConfig] = useState(false);
  
  // 모드 전환
  const [isSwitchingMode, setIsSwitchingMode] = useState(false);
  const [isTradingDay, setIsTradingDay] = useState<boolean | null>(null);
  
  // 투자금 할당 비율
  const [allocationPercent, setAllocationPercent] = useState<number>(80);
  const [isSavingAllocation, setIsSavingAllocation] = useState(false);

  // 서버에서 자동매매 대상 종목 로드
  const loadTradingStocksFromServer = useCallback(async () => {
    setIsLoadingStocks(true);
    try {
      const stocks = await fetchTargetStocksFromServer();
      setTradingStocks(stocks);
    } catch (e) {
      console.error('자동매매 대상 종목 로드 실패:', e);
    } finally {
      setIsLoadingStocks(false);
    }
  }, []);

  // 컴포넌트 마운트 시 서버에서 종목 로드
  useEffect(() => {
    loadTradingStocksFromServer();
  }, [loadTradingStocksFromServer]);

  // initialStocks가 변경되면 서버에 추가
  useEffect(() => {
    if (initialStocks && initialStocks.length > 0) {
      // 서버에 저장
      saveTargetStocksToServer(initialStocks).then(success => {
        if (success) {
          // 저장 성공 후 다시 로드
          loadTradingStocksFromServer();
        }
      });
    }
  }, [initialStocks, loadTradingStocksFromServer]);

  // tradingStocks 변경시 부모에게 알림 (서버 저장은 개별 액션에서 처리)
  useEffect(() => {
    if (onStocksChange) {
      onStocksChange(tradingStocks);
    }
  }, [tradingStocks, onStocksChange]);

  // 전략 설정 변경시 저장 (로컬 + 서버)
  useEffect(() => {
    saveTradingStrategy(strategyConfig);
    
    // 서버에도 저장 (키: trading_strategy_config)
    const saveToServer = async () => {
      try {
        await fetch(`${API_BASE_URL}/auto-trading/settings`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ 'trading_strategy_config': strategyConfig }),
        });
      } catch (e) {
        console.error('전략 설정 서버 저장 실패:', e);
      }
    };
    
    saveToServer();
  }, [strategyConfig]);

  // Heartbeat 조회 (엔진 실행 여부 신뢰성 확인)
  const fetchHeartbeat = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/auto-trading/heartbeat`);
      const data = await response.json();
      if (data.success) {
        setHeartbeat(data);
      }
    } catch (err) {
      console.error('Heartbeat 조회 실패:', err);
    }
  }, []);

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

  // 서버 저장 설정 조회
  const fetchServerSettings = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/auto-trading/settings`);
      const data = await response.json();
      if (data.success && data.settings) {
        setServerSettings({
          auto_start_enabled: data.settings.auto_start_enabled ?? false,
          auto_start_mode: data.settings.auto_start_mode ?? 'manual'
        });
        // 투자금 할당 비율 불러오기
        if (data.settings.allocation_percent !== undefined) {
          setAllocationPercent(data.settings.allocation_percent);
        }
      }
    } catch (err) {
      console.error('서버 설정 조회 실패:', err);
    }
  }, []);

  // 투자금 할당 비율 저장
  const saveAllocationPercent = async (percent: number) => {
    setIsSavingAllocation(true);
    try {
      const response = await fetch(`${API_BASE_URL}/auto-trading/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ allocation_percent: percent })
      });
      const data = await response.json();
      if (data.success) {
        setAllocationPercent(percent);
        // 전략 설정도 업데이트
        setStrategyConfig(prev => ({ ...prev, allocationPercent: percent }));
      } else {
        alert(data.error || '투자금 비율 저장 실패');
      }
    } catch (err) {
      alert('서버 연결 실패');
    } finally {
      setIsSavingAllocation(false);
    }
  };

  // 종목 추가 (수동)
  const handleAddStock = async () => {
    if (!newStockCode.trim()) {
      alert('종목코드를 입력하세요.');
      return;
    }
    
    const code = newStockCode.trim().toUpperCase();
    
    // 중복 체크
    if (tradingStocks.some(s => s.code === code)) {
      alert('이미 등록된 종목입니다.');
      return;
    }
    
    setIsSearchingStock(true);
    try {
      // 종목 정보 조회
      const response = await fetch(`${API_BASE_URL}/stock/${code}`);
      if (response.ok) {
        const data = await response.json();
        const newStock: AutoTradingStock = {
          code: code,
          name: data.name || code,
          basePrice: data.close || data.current_price || 0,
          currentPrice: data.current_price,
          marketCap: data.market_cap || 0,
          addedDate: new Date().toISOString(),
          source: 'manual',
        };
        
        // 서버에 저장
        const success = await saveTargetStocksToServer([newStock]);
        if (success) {
          await loadTradingStocksFromServer();  // 서버에서 다시 로드
          setNewStockCode('');
          setShowAddStock(false);
        } else {
          alert('종목 저장에 실패했습니다.');
        }
      } else {
        alert('종목 정보를 찾을 수 없습니다.');
      }
    } catch (err) {
      alert('종목 조회 중 오류가 발생했습니다.');
    } finally {
      setIsSearchingStock(false);
    }
  };

  // 종목 제거
  const handleRemoveStock = async (code: string) => {
    if (!window.confirm('해당 종목을 자동매매 대상에서 제거하시겠습니까?')) return;
    
    const success = await deleteTargetStocksFromServer([code]);
    if (success) {
      await loadTradingStocksFromServer();  // 서버에서 다시 로드
    } else {
      alert('종목 삭제에 실패했습니다.');
    }
  };

  // 전체 종목 제거
  const handleClearAllStocks = async () => {
    if (!window.confirm('모든 자동매매 대상 종목을 제거하시겠습니까?')) return;
    
    const success = await clearTargetStocksFromServer();
    if (success) {
      setTradingStocks([]);
    } else {
      alert('전체 종목 삭제에 실패했습니다.');
    }
  };

  // 전략 설정 업데이트 핸들러
  const handleUpdateStrategy = (updates: Partial<TradingStrategyConfig>) => {
    setStrategyConfig(prev => ({ ...prev, ...updates }));
  };

  // 매수 시간 추가
  const handleAddBuyTime = () => {
    setStrategyConfig(prev => ({
      ...prev,
      buyTimeConfigs: [
        ...prev.buyTimeConfigs,
        { time: '09:00', enabled: true, orderMethod: 'market' }
      ]
    }));
  };

  // 매수 시간 삭제
  const handleRemoveBuyTime = (index: number) => {
    setStrategyConfig(prev => ({
      ...prev,
      buyTimeConfigs: prev.buyTimeConfigs.filter((_, i) => i !== index)
    }));
  };

  // 매수 시간 변경
  const handleChangeBuyTime = (index: number, time: string) => {
    setStrategyConfig(prev => ({
      ...prev,
      buyTimeConfigs: prev.buyTimeConfigs.map((config, i) => 
        i === index ? { ...config, time } : config
      )
    }));
  };

  // 매수 시간 설정 토글
  const handleToggleBuyTime = (index: number) => {
    setStrategyConfig(prev => ({
      ...prev,
      buyTimeConfigs: prev.buyTimeConfigs.map((config, i) => 
        i === index ? { ...config, enabled: !config.enabled } : config
      )
    }));
  };

  // 매수 방법 변경
  const handleChangeBuyMethod = (index: number, method: BuyTimeConfig['orderMethod']) => {
    setStrategyConfig(prev => ({
      ...prev,
      buyTimeConfigs: prev.buyTimeConfigs.map((config, i) => 
        i === index ? { ...config, orderMethod: method } : config
      )
    }));
  };

  // 매도 조건 토글
  const handleToggleSellCondition = (type: SellCondition['type']) => {
    setStrategyConfig(prev => ({
      ...prev,
      sellConditions: prev.sellConditions.map(cond => 
        cond.type === type ? { ...cond, enabled: !cond.enabled } : cond
      )
    }));
  };

  // 매도 조건 값 변경
  const handleChangeSellValue = (type: SellCondition['type'], value: number) => {
    setStrategyConfig(prev => ({
      ...prev,
      sellConditions: prev.sellConditions.map(cond => 
        cond.type === type ? { ...cond, value } : cond
      )
    }));
  };

  // 서버 저장 설정 업데이트
  const updateServerSettings = async (newSettings: Partial<AutoTradingSettings>) => {
    setIsLoadingSettings(true);
    try {
      const response = await fetch(`${API_BASE_URL}/auto-trading/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newSettings)
      });
      const data = await response.json();
      if (data.success) {
        setServerSettings(prev => ({ ...prev, ...newSettings }));
      } else {
        alert(data.error || '설정 저장 실패');
      }
    } catch (err) {
      alert('서버 연결 실패');
    } finally {
      setIsLoadingSettings(false);
    }
  };
  
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

  // 유니버스 구축 가능 여부 체크 (4PM~6PM은 비활성화)
  const isUniverseBuildDisabled = () => {
    const now = new Date();
    const hour = now.getHours();
    // 오후 4시(16시)~오후 6시(18시) 사이는 비활성화
    return hour >= 16 && hour < 18;
  };

  // 유니버스 구축
  const handleBuildUniverse = async () => {
    if (isUniverseBuildDisabled()) {
      alert('유니버스 구축은 오후 4시~6시 사이에는 실행할 수 없습니다.\n(데이터 수집 중)');
      return;
    }
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
    if (!manualCode) {
      alert('종목코드를 입력하세요');
      return;
    }
    if (!useAutoQuantity && (!manualQuantity || parseInt(manualQuantity) <= 0)) {
      alert('수량을 입력하세요');
      return;
    }
    
    const confirmMsg = useAutoQuantity 
      ? `${manualCode} 종목을 1/${config?.max_positions || 5} 비율로 매수하시겠습니까?`
      : `${manualCode} 종목을 ${manualQuantity}주 매수하시겠습니까?`;
    if (!window.confirm(confirmMsg)) return;
    
    setIsOrdering(true);
    try {
      const response = await fetch(`${API_BASE_URL}/auto-trading/manual-buy`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          code: manualCode, 
          quantity: useAutoQuantity ? 0 : parseInt(manualQuantity),
          auto_quantity: useAutoQuantity
        })
      });
      const data = await response.json();
      if (data.success) {
        const qtyMsg = data.quantity ? ` (${data.quantity}주)` : '';
        alert(`매수 주문 완료: ${data.order_no}${qtyMsg}`);
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

  // 수동 매도 (일괄 매도 포함)
  const handleManualSell = async (code: string | string[], quantity: number = 0) => {
    const isBulk = Array.isArray(code);
    const confirmMsg = isBulk 
      ? `보유 중인 모든 종목(${code.length}개)을 전량 매도하시겠습니까?`
      : `${code} 종목을 ${quantity > 0 ? quantity + '주' : '전량'} 매도하시겠습니까?`;
      
    if (!window.confirm(confirmMsg)) return;
    
    try {
      const response = await fetch(`${API_BASE_URL}/auto-trading/manual-sell`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(isBulk ? { codes: code } : { code, quantity })
      });
      const data = await response.json();
      if (data.success) {
        alert(isBulk ? '일괄 매도 주문이 완료되었습니다.' : `매도 주문 완료: ${data.order_no}`);
        fetchStatus();
      } else {
        alert(data.error || '매도 실패');
      }
    } catch (err) {
      alert('서버 연결 실패');
    }
  };

  // 일괄 매수
  const handleBulkBuy = async () => {
    const watchingCodes = watchingPositions.map(p => p.code);
    if (watchingCodes.length === 0) {
      alert('매수 가능한 감시 중인 종목이 없습니다.');
      return;
    }

    if (!window.confirm(`감시 중인 모든 종목(${watchingCodes.length}개)을 일괄 매수하시겠습니까? (자동 수량 계산)`)) return;

    setIsOrdering(true);
    try {
      const response = await fetch(`${API_BASE_URL}/auto-trading/manual-buy`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          codes: watchingCodes,
          auto_quantity: true
        })
      });
      const data = await response.json();
      if (data.success) {
        alert(`${watchingCodes.length}개 종목에 대한 일괄 매수 주문을 시도했습니다.`);
        fetchStatus();
      } else {
        alert(data.error || '일괄 매수 실패');
      }
    } catch (err) {
      alert('서버 연결 실패');
    } finally {
      setIsOrdering(false);
    }
  };

  // 초기 로드 및 주기적 갱신
  useEffect(() => {
    fetchStatus();
    fetchConfig();
    fetchTradeHistory();
    fetchTradingDayStatus();
    fetchServerSettings();
    fetchHeartbeat();
    
    const interval = setInterval(() => {
      fetchStatus();
      fetchHeartbeat();
    }, 3000); // 3초마다 갱신
    return () => clearInterval(interval);
  }, [fetchStatus, fetchConfig, fetchTradeHistory, fetchTradingDayStatus, fetchServerSettings, fetchHeartbeat]);

  // 엔진 실행 여부 (heartbeat 기반 - 더 신뢰성 있음)
  const isEngineRunning = heartbeat?.is_running && heartbeat?.is_responsive;
  const isEngineResponsive = heartbeat?.is_responsive ?? false;

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

  // 상태별 포지션 분류
  const allPositions: Position[] = status ? Object.values(status.positions) : [];
  const activePositions = allPositions.filter(p => p.state === 'ENTERED');
  const watchingPositions = allPositions.filter(p => p.state === 'WATCHING');
  const pendingPositions = allPositions.filter(p => p.state.includes('PENDING'));
  const closedPositions = allPositions.filter(p => p.state === 'CLOSED');
  const skippedPositions = allPositions.filter(p => p.state === 'SKIPPED');
  const errorPositions = allPositions.filter(p => p.state === 'ERROR');

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
          
          {isEngineRunning ? (
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
              <Power className="w-4 h-4" />
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

      {/* 엔진 상태 & 자동시작 설정 */}
      <div className="bg-[#1a1f2e] border border-slate-800 rounded-2xl p-4 mb-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          {/* 엔진 상태 표시 (Heartbeat 기반) */}
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              {isEngineRunning ? (
                <>
                  <Wifi className="w-5 h-5 text-emerald-400 animate-pulse" />
                  <span className="text-emerald-400 font-bold">
                    엔진 동작중
                    {status?.phase && (
                      <span className="ml-2 px-2 py-0.5 bg-emerald-500/20 rounded text-xs">
                        {status.phase === 'IDLE' ? '대기' :
                         status.phase === 'PREPARING' ? '준비중' :
                         status.phase === 'ENTRY_WINDOW' ? '매수요청' :
                         status.phase === 'MONITORING' ? (activePositions.length > 0 ? '매수완료' : '모니터링') :
                         status.phase === 'EOD_CLOSING' ? '청산준비중' :
                         status.phase === 'CLOSED' ? '전략수행완료' : status.phase}
                      </span>
                    )}
                  </span>
                </>
              ) : heartbeat?.is_running && !isEngineResponsive ? (
                <>
                  <WifiOff className="w-5 h-5 text-amber-400" />
                  <span className="text-amber-400 font-bold">엔진 응답 없음</span>
                </>
              ) : (
                <>
                  <CircleDot className="w-5 h-5 text-slate-500" />
                  <span className="text-slate-500 font-bold">엔진 정지</span>
                </>
              )}
            </div>
            
            {heartbeat && (
              <span className="text-xs text-slate-500">
                마지막 업데이트: {heartbeat.last_update ? new Date(heartbeat.last_update).toLocaleTimeString() : '-'}
              </span>
            )}
          </div>
          
          {/* 자동/수동 시작 토글 */}
          <div className="flex items-center gap-3">
            <span className="text-sm text-slate-400">매일 자동 시작:</span>
            <button
              onClick={() => {
                const newMode = serverSettings.auto_start_mode === 'auto' ? 'manual' : 'auto';
                updateServerSettings({ auto_start_mode: newMode, auto_start_enabled: newMode === 'auto' });
              }}
              disabled={isLoadingSettings}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg transition-all font-bold text-sm ${
                serverSettings.auto_start_mode === 'auto'
                  ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                  : 'bg-slate-700 text-slate-400 border border-slate-600'
              }`}
            >
              {serverSettings.auto_start_mode === 'auto' ? (
                <>
                  <ToggleRight className="w-5 h-5" />
                  자동
                </>
              ) : (
                <>
                  <ToggleLeft className="w-5 h-5" />
                  수동
                </>
              )}
            </button>
            <span className="text-xs text-slate-500">
              {serverSettings.auto_start_mode === 'auto' 
                ? '매 거래일 08:40 자동 시작' 
                : '수동으로 시작 버튼 클릭 필요'}
            </span>
          </div>
        </div>
      </div>

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
          onClick={() => setShowAddStock(!showAddStock)}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/20 transition-all text-sm font-bold"
        >
          <PlusCircle className="w-4 h-4" />
          종목 추가
        </button>
        
        <button
          onClick={handleRefreshPositions}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-500/10 border border-blue-500/30 text-blue-400 hover:bg-blue-500/20 transition-all text-sm font-bold"
        >
          <RefreshCw className="w-4 h-4" />
          포지션 동기화
        </button>
        
        <button
          onClick={() => setShowStrategySettings(!showStrategySettings)}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold transition-all ${
            showStrategySettings 
              ? 'bg-violet-500/30 border border-violet-500/50 text-violet-300' 
              : 'bg-violet-500/10 border border-violet-500/30 text-violet-400 hover:bg-violet-500/20'
          }`}
        >
          <Settings className="w-4 h-4" />
          매매 전략 설정
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

      {/* 투자금 할당 비율 설정 */}
      <div className="bg-violet-500/10 border border-violet-500/30 rounded-2xl p-4 mb-6">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-violet-500/20 flex items-center justify-center">
              <Wallet className="w-5 h-5 text-violet-400" />
            </div>
            <div>
              <h3 className="text-white font-bold text-sm">투자금 할당 비율</h3>
              <p className="text-xs text-slate-400">총 자산 중 자동매매에 사용할 비율</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <input
                type="range"
                min="10"
                max="100"
                step="10"
                value={strategyConfig.allocationPercent}
                onChange={(e) => handleUpdateStrategy({ allocationPercent: parseInt(e.target.value) })}
                className="w-32 accent-violet-500"
              />
              <div className="flex items-center bg-slate-800 rounded-lg px-3 py-1.5 min-w-[80px]">
                <span className="text-white text-sm font-bold">{strategyConfig.allocationPercent}</span>
                <span className="text-violet-400 font-bold text-sm ml-1">%</span>
              </div>
            </div>
            <button
              onClick={() => saveAllocationPercent(strategyConfig.allocationPercent)}
              disabled={isSavingAllocation}
              className="px-4 py-2 bg-violet-500/20 hover:bg-violet-500 text-violet-400 hover:text-white border border-violet-500/30 rounded-lg text-xs font-bold transition-all disabled:opacity-50"
            >
              {isSavingAllocation ? <Loader2 className="w-4 h-4 animate-spin" /> : '서버 저장'}
            </button>
          </div>
        </div>
        <div className="mt-3 text-xs text-slate-500">
          💡 총자산의 <span className="text-violet-400 font-bold">{strategyConfig.allocationPercent}%</span>를 자동매매에 사용하고, 
          각 종목당 <span className="text-point-cyan font-bold">1/{strategyConfig.maxPositions}</span> 균등 배분합니다.
          (종목당 약 {((strategyConfig.allocationPercent / strategyConfig.maxPositions)).toFixed(1)}%)
        </div>
      </div>

      {/* 종목 추가 패널 */}
      {showAddStock && (
        <div className="bg-[#1a1f2e] border border-emerald-500/30 rounded-2xl p-4 mb-6 animate-in slide-in-from-top-2 duration-200">
          <h3 className="text-white font-bold mb-4 flex items-center gap-2">
            <PlusCircle className="w-5 h-5 text-emerald-400" />
            종목 추가 (수동)
          </h3>
          <div className="relative">
            <div className="flex gap-3">
              <div className="flex-1 relative">
                <input
                  type="text"
                  value={newStockCode}
                  onChange={async (e) => {
                    const value = e.target.value;
                    setNewStockCode(value);
                    
                    // 검색어가 2자 이상이면 검색 실행
                    if (value.length >= 2) {
                      await loadStockList();
                      const results = searchStocks(value);
                      setStockSearchResults(results.map(r => ({ code: r.code, name: r.name })));
                      setShowSearchResults(results.length > 0);
                    } else {
                      setStockSearchResults([]);
                      setShowSearchResults(false);
                    }
                  }}
                  onFocus={async () => {
                    if (newStockCode.length >= 2) {
                      await loadStockList();
                      const results = searchStocks(newStockCode);
                      setStockSearchResults(results.map(r => ({ code: r.code, name: r.name })));
                      setShowSearchResults(results.length > 0);
                    }
                  }}
                  onBlur={() => {
                    // 클릭 처리를 위해 딜레이
                    setTimeout(() => setShowSearchResults(false), 200);
                  }}
                  onKeyDown={(e) => e.key === 'Enter' && handleAddStock()}
                  placeholder="종목코드 또는 종목명 입력 (예: 005930 또는 삼성전자)"
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-2 text-white text-sm focus:outline-none focus:border-emerald-500"
                />
                
                {/* 검색 결과 드롭다운 */}
                {showSearchResults && stockSearchResults.length > 0 && (
                  <div className="absolute top-full left-0 right-0 mt-1 bg-slate-800 border border-slate-700 rounded-lg shadow-xl z-50 max-h-60 overflow-y-auto">
                    {stockSearchResults.map((stock) => (
                      <button
                        key={stock.code}
                        onClick={() => {
                          setNewStockCode(stock.code);
                          setShowSearchResults(false);
                        }}
                        className="w-full px-4 py-2 text-left hover:bg-slate-700 transition-colors flex justify-between items-center"
                      >
                        <span className="text-white">{stock.name}</span>
                        <span className="text-slate-400 text-sm">{stock.code}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <button
                onClick={handleAddStock}
                disabled={isSearchingStock}
                className="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white font-bold rounded-lg transition-all flex items-center gap-2 disabled:opacity-50"
              >
                {isSearchingStock ? <Loader2 className="w-4 h-4 animate-spin" /> : <PlusCircle className="w-4 h-4" />}
                추가
              </button>
              <button
                onClick={() => setShowAddStock(false)}
                className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 font-bold rounded-lg transition-all"
              >
                닫기
              </button>
            </div>
          </div>
          <p className="text-xs text-slate-500 mt-2">
            💡 종목코드(6자리) 또는 종목명을 입력하면 검색됩니다. AI추천 페이지에서 종목을 선택하여 추가할 수도 있습니다.
          </p>
        </div>
      )}

      {/* 매매 전략 설정 패널 (신규) */}
      {showStrategySettings && (
        <div className="bg-[#1a1f2e] border border-violet-500/30 rounded-2xl p-4 mb-6 animate-in slide-in-from-top-2 duration-200">
          <h3 className="text-white font-bold mb-4 flex items-center gap-2">
            <Settings className="w-5 h-5 text-violet-400" />
            커스텀 매매 전략 설정
          </h3>
          
          {/* 매수 시간 및 방법 설정 */}
          <div className="mb-6">
            <h4 className="text-sm font-bold text-slate-300 mb-3 flex items-center gap-2">
              <ShoppingCart className="w-4 h-4 text-point-cyan" />
              매수 시간 설정
            </h4>
            <div className="bg-slate-800/50 rounded-xl p-4">
              <p className="text-xs text-slate-400 mb-4">매수할 시간을 자유롭게 추가/삭제할 수 있습니다. (24시간 형식, HH:MM)</p>
              <div className="space-y-3">
                {strategyConfig.buyTimeConfigs.map((timeConfig, idx) => (
                  <div key={idx} className="flex items-center gap-3 flex-wrap">
                    {/* 활성화 토글 */}
                    <button
                      onClick={() => handleToggleBuyTime(idx)}
                      className={`p-2 rounded-lg transition-all ${
                        timeConfig.enabled
                          ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                          : 'bg-slate-700 text-slate-400 border border-slate-600'
                      }`}
                      title={timeConfig.enabled ? '비활성화' : '활성화'}
                    >
                      {timeConfig.enabled ? <ToggleRight className="w-4 h-4" /> : <ToggleLeft className="w-4 h-4" />}
                    </button>
                    
                    {/* 시간 입력 (시:분) */}
                    <input
                      type="time"
                      value={timeConfig.time}
                      onChange={(e) => handleChangeBuyTime(idx, e.target.value)}
                      className="bg-slate-700 text-white px-3 py-2 rounded-lg text-sm font-mono border border-slate-600 focus:border-violet-500 focus:outline-none"
                    />
                    
                    {/* 매수 방법 선택 */}
                    <select
                      value={timeConfig.orderMethod}
                      onChange={(e) => handleChangeBuyMethod(idx, e.target.value as BuyTimeConfig['orderMethod'])}
                      disabled={!timeConfig.enabled}
                      className="bg-slate-700 text-white px-3 py-2 rounded-lg text-sm border border-slate-600 focus:border-violet-500 focus:outline-none disabled:opacity-50"
                    >
                      <option value="market">시장가</option>
                      <option value="open_price">시가 지정가</option>
                      <option value="ask_plus_2tick">ASK+2틱</option>
                    </select>
                    
                    {/* 삭제 버튼 */}
                    <button
                      onClick={() => handleRemoveBuyTime(idx)}
                      className="p-2 rounded-lg bg-rose-500/20 text-rose-400 hover:bg-rose-500/30 transition-all"
                      title="삭제"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))}
                
                {/* 시간 추가 버튼 */}
                <button
                  onClick={handleAddBuyTime}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-violet-500/20 text-violet-400 hover:bg-violet-500/30 border border-violet-500/30 transition-all text-sm font-bold"
                >
                  <PlusCircle className="w-4 h-4" />
                  매수 시간 추가
                </button>
              </div>
              
              {strategyConfig.buyTimeConfigs.length === 0 && (
                <p className="text-amber-400 text-xs mt-2">⚠️ 매수 시간이 설정되지 않았습니다. 최소 1개 이상의 시간을 추가해주세요.</p>
              )}
            </div>
          </div>
          
          {/* 매도 조건 설정 */}
          <div className="mb-6">
            <h4 className="text-sm font-bold text-slate-300 mb-3 flex items-center gap-2">
              <Banknote className="w-4 h-4 text-rose-400" />
              매도 기준 및 방법 (복수 선택 가능)
            </h4>
            <div className="bg-slate-800/50 rounded-xl p-4">
              <p className="text-xs text-slate-400 mb-4">여러 조건을 동시에 활성화하면, 먼저 충족되는 조건에 따라 매도됩니다.</p>
              <div className="space-y-3">
                {strategyConfig.sellConditions.map((condition, idx) => (
                  <div key={idx} className="flex items-center gap-4 flex-wrap">
                    {/* 활성화 토글 */}
                    <button
                      onClick={() => handleToggleSellCondition(condition.type)}
                      className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-bold transition-all min-w-[120px] ${
                        condition.enabled
                          ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                          : 'bg-slate-700 text-slate-400 border border-slate-600'
                      }`}
                    >
                      {condition.enabled ? <ToggleRight className="w-4 h-4" /> : <ToggleLeft className="w-4 h-4" />}
                      {condition.type === 'take_profit' && '익절'}
                      {condition.type === 'trailing_stop' && '고가대비'}
                      {condition.type === 'stop_loss' && '손절'}
                      {condition.type === 'eod_close' && '종가매도'}
                    </button>
                    
                    {/* 값 입력 (종가매도 제외) */}
                    {condition.type !== 'eod_close' && (
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-slate-400">
                          {condition.type === 'take_profit' && '매수가 대비'}
                          {condition.type === 'trailing_stop' && '고가 대비'}
                          {condition.type === 'stop_loss' && '매수가 대비'}
                        </span>
                        <div className="flex items-center bg-slate-700 rounded-lg px-2 py-1">
                          <span className="text-slate-400 text-sm">
                            {condition.type === 'take_profit' ? '+' : '-'}
                          </span>
                          <input
                            type="number"
                            value={condition.value || 0}
                            onChange={(e) => handleChangeSellValue(condition.type, Math.abs(parseFloat(e.target.value) || 0))}
                            disabled={!condition.enabled}
                            className="w-12 bg-transparent text-white text-sm text-right outline-none disabled:opacity-50"
                          />
                          <span className="text-slate-400 text-sm ml-1">%</span>
                        </div>
                        <span className="text-xs text-slate-500">
                          {condition.type === 'take_profit' && '이상 시 매도 (익절)'}
                          {condition.type === 'trailing_stop' && '하락 시 매도'}
                          {condition.type === 'stop_loss' && '이하 시 매도 (손절)'}
                        </span>
                      </div>
                    )}
                    
                    {condition.type === 'eod_close' && (
                      <span className="text-xs text-slate-500">장 마감 전 전량 매도 (15:15~15:20)</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
          
          {/* 최대 포지션 수 설정 */}
          <div className="mb-4">
            <h4 className="text-sm font-bold text-slate-300 mb-3 flex items-center gap-2">
              <Target className="w-4 h-4 text-amber-400" />
              최대 포지션 수
            </h4>
            <div className="bg-slate-800/50 rounded-xl p-4 flex items-center gap-4">
              <input
                type="range"
                min="1"
                max="10"
                value={strategyConfig.maxPositions}
                onChange={(e) => handleUpdateStrategy({ maxPositions: parseInt(e.target.value) })}
                className="w-48 accent-amber-500"
              />
              <div className="flex items-center bg-slate-700 rounded-lg px-3 py-1.5">
                <span className="text-white text-sm font-bold">{strategyConfig.maxPositions}</span>
                <span className="text-amber-400 font-bold text-sm ml-1">개</span>
              </div>
              <span className="text-xs text-slate-500">종목당 약 {(strategyConfig.allocationPercent / strategyConfig.maxPositions).toFixed(1)}% 배분</span>
            </div>
          </div>
          
          {/* 전략 요약 */}
          <div className="bg-slate-900/50 border border-slate-700 rounded-xl p-4 mt-4">
            <h4 className="text-sm font-bold text-white mb-2">📋 현재 전략 요약</h4>
            <div className="text-xs text-slate-400 space-y-1">
              <p>• 매수 시간: {strategyConfig.buyTimeConfigs.filter(c => c.enabled).map(c => c.time).join(', ') || '없음'}</p>
              <p>• 매수 방법: {strategyConfig.buyTimeConfigs.filter(c => c.enabled).map(c => 
                c.orderMethod === 'market' ? '시장가' : c.orderMethod === 'open_price' ? '시가 지정가' : 'ASK+2틱'
              ).join(', ') || '-'}</p>
              <p>• 매도 조건: {strategyConfig.sellConditions.filter(c => c.enabled).map(c => {
                if (c.type === 'take_profit') return `익절 +${c.value}%`;
                if (c.type === 'trailing_stop') return `고가대비 -${c.value}%`;
                if (c.type === 'stop_loss') return `손절 -${c.value}%`;
                return '종가매도';
              }).join(', ') || '없음'}</p>
              <p>• 최대 포지션: {strategyConfig.maxPositions}개 (종목당 {(strategyConfig.allocationPercent / strategyConfig.maxPositions).toFixed(1)}%)</p>
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
                    <th className="text-left py-2 px-2">청산 사유</th>
                  </tr>
                </thead>
                <tbody>
                  {tradeHistory.map((trade) => {
                    // 청산 사유 배지 스타일
                    const getExitReasonBadge = (reason: string | null) => {
                      if (!reason) return null;
                      const reasonMap: { [key: string]: { label: string; className: string } } = {
                        'TP': { label: '✅ 익절 (TP)', className: 'bg-emerald-500/20 text-emerald-400' },
                        'TAKE_PROFIT': { label: '✅ 익절 (TP)', className: 'bg-emerald-500/20 text-emerald-400' },
                        'SL': { label: '🛑 손절 (SL)', className: 'bg-rose-500/20 text-rose-400' },
                        'STOP_LOSS': { label: '🛑 손절 (SL)', className: 'bg-rose-500/20 text-rose-400' },
                        'EOD': { label: '🕐 장마감 청산', className: 'bg-amber-500/20 text-amber-400' },
                        'EOD_CLOSE': { label: '🕐 장마감 청산', className: 'bg-amber-500/20 text-amber-400' },
                        'MANUAL': { label: '👤 수동 청산', className: 'bg-blue-500/20 text-blue-400' },
                        'AUTO': { label: '🤖 자동', className: 'bg-slate-500/20 text-slate-400' },
                      };
                      const config = reasonMap[reason.toUpperCase()] || { label: reason, className: 'bg-slate-500/20 text-slate-400' };
                      return (
                        <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${config.className}`}>
                          {config.label}
                        </span>
                      );
                    };
                    
                    return (
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
                        <td className="py-2 px-2">{getExitReasonBadge(trade.exit_reason) || '-'}</td>
                      </tr>
                    );
                  })}
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
          {activePositions.length > 0 && (
            <button
              onClick={() => handleManualSell(activePositions.map(p => p.code))}
              className="bg-rose-500/20 hover:bg-rose-500 text-rose-400 hover:text-white px-3 py-1.5 rounded-lg text-sm font-bold transition-all flex items-center gap-2"
            >
              <ShoppingCart className="w-4 h-4" />
              일괄매도
            </button>
          )}
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
                  <th className="text-right py-3 px-4">총매수금액</th>
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
                    <td className="py-3 px-4 text-right text-slate-300">{formatPrice(pos.entry_price * pos.quantity)}원</td>
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

      {/* 전체 종목 상태 (엔진 Universe) */}
      <div className="bg-[#1a1f2e] border border-slate-800 rounded-2xl mb-6 overflow-hidden">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-3">
            <h3 className="text-white font-bold flex items-center gap-2">
              <Target className="w-5 h-5 text-violet-400" />
              자동매매 대상 종목 ({allPositions.length})
            </h3>
            {/* 삭제 버튼들 */}
            <div className="flex items-center gap-2">
              <button
                onClick={handleBulkBuy}
                disabled={watchingPositions.length === 0 || isOrdering}
                className="bg-emerald-500/20 hover:bg-emerald-600 text-emerald-400 hover:text-white px-3 py-1 rounded-lg text-xs font-bold transition-all flex items-center gap-1 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ShoppingCart className="w-3.5 h-3.5" />
                일괄매수
              </button>
              {allPositions.length > 0 && (
                <>
                  <button
                    onClick={() => {
                    if (confirm('청산 완료 및 건너뜀 종목을 모두 삭제하시겠습니까?')) {
                      const toRemove = allPositions
                        .filter(p => p.state === 'CLOSED' || p.state === 'SKIPPED')
                        .map(p => p.code);
                      if (toRemove.length > 0) {
                        fetch('/api/auto-trading/positions/remove', {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({ codes: toRemove })
                        }).then(() => fetchStatus());
                      }
                    }
                  }}
                  className="text-xs px-2 py-1 rounded bg-slate-700/50 hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
                >
                  완료된 종목 정리
                </button>
                <button
                  onClick={handleClearAllStocks}
                  className="text-xs px-2 py-1 rounded bg-rose-500/20 hover:bg-rose-500 text-rose-400 hover:text-white transition-colors flex items-center gap-1"
                >
                  <Trash2 className="w-3 h-3" />
                  전체 삭제
                </button>
              </>
            )}
          </div>
        </div>
          {/* 상태별 요약 */}
          <div className="flex flex-wrap gap-2 text-xs">
            {watchingPositions.length > 0 && (
              <span className="px-2 py-1 rounded-full bg-amber-500/20 text-amber-400">
                감시중 {watchingPositions.length}
              </span>
            )}
            {pendingPositions.length > 0 && (
              <span className="px-2 py-1 rounded-full bg-blue-500/20 text-blue-400">
                주문대기 {pendingPositions.length}
              </span>
            )}
            {activePositions.length > 0 && (
              <span className="px-2 py-1 rounded-full bg-emerald-500/20 text-emerald-400">
                보유중 {activePositions.length}
              </span>
            )}
            {closedPositions.length > 0 && (
              <span className="px-2 py-1 rounded-full bg-slate-500/20 text-slate-400">
                청산 {closedPositions.length}
              </span>
            )}
            {skippedPositions.length > 0 && (
              <span className="px-2 py-1 rounded-full bg-rose-500/20 text-rose-400">
                건너뜀 {skippedPositions.length}
              </span>
            )}
            {errorPositions.length > 0 && (
              <span className="px-2 py-1 rounded-full bg-rose-500/20 text-rose-400 animate-pulse">
                오류 {errorPositions.length}
              </span>
            )}
          </div>
        </div>

        {/* 휴장일 경고 */}
        {isTradingDay === false && (
          <div className="p-4 bg-amber-500/10 border-b border-amber-500/30">
            <div className="flex items-center gap-2 text-amber-400 font-bold">
              <AlertTriangle className="w-5 h-5" />
              오늘은 휴장일입니다. 매매 주문이 불가능합니다.
            </div>
          </div>
        )}
        
        {allPositions.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-500 border-b border-slate-800 bg-slate-800/30">
                  <th className="text-left py-3 px-4">종목</th>
                  <th className="text-left py-3 px-4">상태</th>
                  <th className="text-right py-3 px-4">전일종가</th>
                  <th className="text-right py-3 px-4">현재가</th>
                  <th className="text-right py-3 px-4">수량</th>
                  <th className="text-right py-3 px-4">갭/손익</th>
                  <th className="text-left py-3 px-4">상세정보</th>
                  <th className="text-center py-3 px-4">액션</th>
                </tr>
              </thead>
              <tbody>
                {allPositions.map((pos) => {
                  const gapRate = pos.prev_close > 0 && pos.current_price > 0
                    ? ((pos.current_price - pos.prev_close) / pos.prev_close * 100)
                    : 0;
                  
                  // 상태별 상세 정보 텍스트
                  const getStatusDetail = () => {
                    switch (pos.state) {
                      case 'WATCHING':
                        return `갭 확인: ${pos.gap_confirms}/${config?.gap_confirm_count || 2}`;
                      case 'ENTRY_PENDING':
                        return pos.order_id ? `주문번호: ${pos.order_id}` : '매수 주문 접수됨';
                      case 'ENTERED':
                        return pos.entry_time ? `진입: ${formatTime(pos.entry_time)}` : '보유 중';
                      case 'EXIT_PENDING':
                        return pos.order_id ? `청산주문: ${pos.order_id}` : '매도 주문 접수됨';
                      case 'CLOSED':
                        return pos.exit_reason || '청산 완료';
                      case 'SKIPPED':
                        return pos.exit_reason || '조건 미달';
                      case 'ERROR':
                        return pos.error_message || '알 수 없는 오류';
                      default:
                        return '-';
                    }
                  };
                  
                  return (
                    <tr key={pos.code} className={`border-b border-slate-800/50 hover:bg-slate-800/30 ${
                      pos.state === 'ERROR' ? 'bg-rose-500/5' : ''
                    }`}>
                      <td className="py-3 px-4">
                        <div className="font-bold text-white">{pos.name || pos.code}</div>
                        <div className="text-xs text-slate-500">{pos.code}</div>
                      </td>
                      <td className="py-3 px-4"><StateBadge state={pos.state} /></td>
                      <td className="py-3 px-4 text-right text-slate-400">{formatPrice(pos.prev_close)}원</td>
                      <td className="py-3 px-4 text-right text-white">
                        {pos.current_price > 0 ? `${formatPrice(pos.current_price)}원` : '-'}
                      </td>
                      <td className="py-3 px-4 text-right">
                        {pos.quantity > 0 ? (
                          <span className="text-white font-bold">{pos.quantity}주</span>
                        ) : pos.pending_quantity > 0 ? (
                          <span className="text-blue-400">{pos.pending_quantity}주 (대기)</span>
                        ) : (
                          <span className="text-slate-500">-</span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-right">
                        {pos.state === 'WATCHING' ? (
                          <span className={`font-bold ${gapRate >= 2 ? 'text-emerald-400' : 'text-slate-500'}`}>
                            갭 {formatPercent(gapRate)}
                          </span>
                        ) : pos.state === 'ENTERED' && pos.unrealized_pnl !== 0 ? (
                          <span className={`font-bold ${pos.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                            {formatPercent(pos.unrealized_pnl_rate)}
                          </span>
                        ) : (
                          <span className="text-slate-500">-</span>
                        )}
                      </td>
                      <td className="py-3 px-4">
                        <div className={`text-xs ${pos.state === 'ERROR' ? 'text-rose-400' : 'text-slate-400'}`}>
                          {getStatusDetail()}
                        </div>
                        {pos.retry_count > 0 && (
                          <div className="text-xs text-amber-400">재시도: {pos.retry_count}회</div>
                        )}
                      </td>
                      <td className="py-3 px-4 text-center">
                        <div className="flex items-center justify-center gap-1">
                          {(pos.state === 'WATCHING' || pos.state === 'IDLE') && (
                            <button
                              onClick={() => {
                                setManualCode(pos.code);
                                setUseAutoQuantity(true);  // 자동 수량 활성화
                                setManualQuantity('');
                              }}
                              disabled={isTradingDay === false}
                              className="bg-point-cyan/10 hover:bg-point-cyan text-point-cyan hover:text-white border border-point-cyan/30 px-2 py-1 rounded-lg text-xs font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                              수동매수
                            </button>
                          )}
                          {pos.state === 'ENTERED' && (
                            <button
                              onClick={() => handleManualSell(pos.code, 0)}
                              disabled={isTradingDay === false}
                              className="bg-rose-500/10 hover:bg-rose-500 text-rose-400 hover:text-white border border-rose-500/30 px-2 py-1 rounded-lg text-xs font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                              청산
                            </button>
                          )}
                          {pos.state === 'ERROR' && (
                            <span className="text-xs text-rose-400">확인필요</span>
                          )}
                          {/* 삭제 버튼 - 보유 중이 아닌 종목만 (EXIT_PENDING은 오류로 청산완료 가능) */}
                          {pos.state !== 'ENTERED' && pos.state !== 'ENTRY_PENDING' && (
                            <button
                              onClick={() => {
                                if (confirm(`${pos.name || pos.code} 종목을 목록에서 삭제하시겠습니까?`)) {
                                  fetch('/api/auto-trading/positions/remove', {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify({ codes: [pos.code] })
                                  }).then(() => fetchStatus());
                                }
                              }}
                              className="text-slate-500 hover:text-rose-400 p-1 transition-colors"
                              title="목록에서 삭제"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-8 text-center text-slate-500">
            종목이 없습니다. "유니버스 구축" 버튼을 눌러 종목을 추가하세요.
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
          
          {/* 자동 수량 토글 */}
          <div className="min-w-[140px]">
            <label className="text-xs text-slate-500 mb-1 block">수량 계산</label>
            <button
              onClick={() => setUseAutoQuantity(!useAutoQuantity)}
              className={`w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-sm font-bold transition-all ${
                useAutoQuantity
                  ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                  : 'bg-slate-800 text-slate-400 border border-slate-700'
              }`}
            >
              {useAutoQuantity ? (
                <>
                  <ToggleRight className="w-5 h-5" />
                  자동 (1/{config?.max_positions || 5})
                </>
              ) : (
                <>
                  <ToggleLeft className="w-5 h-5" />
                  수동 입력
                </>
              )}
            </button>
          </div>
          
          {!useAutoQuantity && (
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
          )}
          
          <button
            onClick={handleManualBuy}
            disabled={isOrdering}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-point-cyan text-white font-bold hover:bg-point-cyan/90 transition-all disabled:opacity-50"
          >
            {isOrdering ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShoppingCart className="w-4 h-4" />}
            매수
          </button>
        </div>
        
        {/* 자동 수량 설명 */}
        {useAutoQuantity && status && (
          <p className="mt-3 text-xs text-slate-500">
            💡 총 자산 {formatPrice(status.total_asset)}원 ÷ {config?.max_positions || 5} = 
            종목당 약 {formatPrice(Math.floor((status.total_asset || 0) / (config?.max_positions || 5)))}원 투자
          </p>
        )}
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

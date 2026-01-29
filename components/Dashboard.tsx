import React, { useState, useEffect, useCallback, useRef } from 'react';
import { 
  Play,
  Square,
  RefreshCw,
  Database,
  Calendar,
  Clock,
  CheckCircle,
  XCircle,
  AlertCircle,
  Loader2,
  FolderOpen,
  Activity
} from 'lucide-react';
import { useResponsive } from '../hooks/useResponsive';

const API_BASE_URL = '/api';

interface CrawlProgress {
  current: number;
  total: number;
  current_code: string | null;
  current_name: string | null;
  success_count: number;
  fail_count: number;
  started_at: string | null;
  eta_seconds: number | null;
}

interface SchedulerStatus {
  eod_done_today: boolean;
  intraday_done_today: boolean;
  inference_done_today: boolean;
  last_check_date: string | null;
  crawling_status: string | null;
  crawling_start_time: string | null;
  crawling_error: string | null;
  last_crawl_completed_at: string | null;
  last_crawl_mode: string | null;
  last_crawl_date_range: string | null;
  last_crawl_duration: number | null;
  crawl_progress: CrawlProgress | null;
}

interface CrawlDateInfo {
  date: string;
  hasData: boolean;
}

export const Dashboard: React.FC = () => {
  const { isMobile } = useResponsive();
  const [schedulerStatus, setSchedulerStatus] = useState<SchedulerStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [crawlDates, setCrawlDates] = useState<CrawlDateInfo[]>([]);
  const [isLoadingDates, setIsLoadingDates] = useState(false);
  
  // Manual crawl form
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [crawlMode, setCrawlMode] = useState<'eod' | 'intraday'>('eod');
  const [isStartingCrawl, setIsStartingCrawl] = useState(false);
  
  // SSE connection
  const eventSourceRef = useRef<EventSource | null>(null);

  const loadStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/scheduler/status`);
      if (res.ok) {
        const data = await res.json();
        setSchedulerStatus(data);
      }
      setLastUpdated(new Date());
    } catch (error) {
      console.error('스케줄러 상태 로딩 실패:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const loadRecentDates = useCallback(async () => {
    setIsLoadingDates(true);
    try {
      // Get last 30 dates from crawl data API
      const res = await fetch(`${API_BASE_URL}/crawl-dates?limit=30`);
      if (res.ok) {
        const data = await res.json();
        setCrawlDates(data.dates || []);
      }
    } catch (error) {
      console.error('수집 날짜 로딩 실패:', error);
    } finally {
      setIsLoadingDates(false);
    }
  }, []);

  // SSE 연결 관리
  useEffect(() => {
    const connectSSE = () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      
      const es = new EventSource(`${API_BASE_URL}/crawl-progress/stream`);
      
      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'crawl_progress' && data.progress) {
            setSchedulerStatus(prev => prev ? {
              ...prev,
              crawling_status: data.status,
              crawl_progress: data.progress
            } : null);
          }
        } catch (e) {
          console.error('SSE 파싱 오류:', e);
        }
      };
      
      es.onerror = () => {
        es.close();
        // 5초 후 재연결 시도
        setTimeout(connectSSE, 5000);
      };
      
      eventSourceRef.current = es;
    };
    
    connectSSE();
    
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  useEffect(() => {
    loadStatus();
    loadRecentDates();
    const interval = setInterval(loadStatus, 5000); // 5초마다 상태 갱신
    return () => clearInterval(interval);
  }, [loadStatus, loadRecentDates]);

  const handleTriggerTask = async (task: 'eod' | 'intraday' | 'inference') => {
    try {
      const res = await fetch(`${API_BASE_URL}/scheduler/trigger?task=${task}`, {
        method: 'POST'
      });
      if (res.ok) {
        await loadStatus();
      } else {
        const data = await res.json();
        alert(data.error || '작업 시작 실패');
      }
    } catch (error) {
      console.error('작업 트리거 실패:', error);
      alert('작업 시작 중 오류가 발생했습니다.');
    }
  };

  const handleManualCrawl = async () => {
    if (!startDate) {
      alert('시작 날짜를 입력하세요.');
      return;
    }
    setIsStartingCrawl(true);
    try {
      const res = await fetch(`${API_BASE_URL}/crawl`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          start_date: startDate,
          end_date: endDate || startDate,
          mode: crawlMode
        })
      });
      if (res.ok) {
        await loadStatus();
        setStartDate('');
        setEndDate('');
      } else {
        const data = await res.json();
        alert(data.error || '수집 시작 실패');
      }
    } catch (error) {
      console.error('수집 시작 실패:', error);
      alert('수집 시작 중 오류가 발생했습니다.');
    } finally {
      setIsStartingCrawl(false);
    }
  };

  const formatDuration = (seconds: number | null) => {
    if (!seconds) return '-';
    const mins = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return mins > 0 ? `${mins}분 ${secs}초` : `${secs}초`;
  };

  const formatDateTime = (isoStr: string | null) => {
    if (!isoStr) return '-';
    try {
      const d = new Date(isoStr);
      return d.toLocaleString('ko-KR');
    } catch {
      return isoStr;
    }
  };

  const isCrawling = schedulerStatus?.crawling_status != null;

  if (isLoading && !schedulerStatus) {
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
    <div className={`space-y-${isMobile ? '4' : '6'}`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className={`${isMobile ? 'text-xl' : 'text-3xl'} font-black text-white tracking-tight`}>데이터 수집 관리</h1>
          <p className={`text-slate-500 font-bold mt-1 ${isMobile ? 'text-xs' : ''}`}>KRX 주가 데이터 수집 현황</p>
        </div>
        <button 
          onClick={() => { loadStatus(); loadRecentDates(); }}
          disabled={isLoading}
          className={`flex items-center gap-2 bg-[#1a1f2e] border border-slate-700 text-slate-400 hover:text-white hover:border-slate-600 ${isMobile ? 'px-3 py-1.5 text-xs' : 'px-4 py-2 text-sm'} rounded-xl font-bold transition-all disabled:opacity-50`}
        >
          <RefreshCw className={`${isMobile ? 'w-3 h-3' : 'w-4 h-4'} ${isLoading ? 'animate-spin' : ''}`} />
          {!isMobile && '새로고침'}
        </button>
      </div>

      {lastUpdated && (
        <div className="text-[10px] text-slate-600 font-bold uppercase tracking-wider">
          마지막 업데이트: {lastUpdated.toLocaleTimeString('ko-KR')}
        </div>
      )}

      {/* Current Status Card */}
      <div className={`bg-[#1a1f2e] border ${isCrawling ? 'border-amber-500/50' : 'border-slate-800'} rounded-2xl ${isMobile ? 'p-4' : 'p-6'}`}>
        <div className="flex items-center justify-between mb-4">
          <h3 className={`${isMobile ? 'text-base' : 'text-lg'} font-bold text-white flex items-center gap-2`}>
            <Database className={`${isMobile ? 'w-4 h-4' : 'w-5 h-5'} text-point-cyan`} />
            현재 상태
          </h3>
          {isCrawling && (
            <span className="flex items-center gap-2 px-3 py-1 rounded-lg bg-amber-500/10 text-amber-400 text-xs font-bold">
              <Loader2 className="w-3 h-3 animate-spin" />
              {schedulerStatus?.crawling_status?.toUpperCase()} 수집 중
            </span>
          )}
        </div>

        <div className={`grid ${isMobile ? 'grid-cols-2 gap-3' : 'grid-cols-4 gap-4'}`}>
          <div className="bg-[#0d1117] rounded-xl p-3">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">EOD 수집</div>
            <div className="flex items-center gap-2">
              {schedulerStatus?.eod_done_today ? (
                <CheckCircle className="w-4 h-4 text-emerald-400" />
              ) : (
                <XCircle className="w-4 h-4 text-slate-500" />
              )}
              <span className={`text-sm font-bold ${schedulerStatus?.eod_done_today ? 'text-emerald-400' : 'text-slate-500'}`}>
                {schedulerStatus?.eod_done_today ? '완료' : '미완료'}
              </span>
            </div>
          </div>
          
          <div className="bg-[#0d1117] rounded-xl p-3">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Intraday</div>
            <div className="flex items-center gap-2">
              {schedulerStatus?.intraday_done_today ? (
                <CheckCircle className="w-4 h-4 text-emerald-400" />
              ) : (
                <XCircle className="w-4 h-4 text-slate-500" />
              )}
              <span className={`text-sm font-bold ${schedulerStatus?.intraday_done_today ? 'text-emerald-400' : 'text-slate-500'}`}>
                {schedulerStatus?.intraday_done_today ? '완료' : '미완료'}
              </span>
            </div>
          </div>

          <div className="bg-[#0d1117] rounded-xl p-3">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">AI 예측</div>
            <div className="flex items-center gap-2">
              {schedulerStatus?.inference_done_today ? (
                <CheckCircle className="w-4 h-4 text-emerald-400" />
              ) : (
                <XCircle className="w-4 h-4 text-slate-500" />
              )}
              <span className={`text-sm font-bold ${schedulerStatus?.inference_done_today ? 'text-emerald-400' : 'text-slate-500'}`}>
                {schedulerStatus?.inference_done_today ? '완료' : '미완료'}
              </span>
            </div>
          </div>

          <div className="bg-[#0d1117] rounded-xl p-3">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">마지막 체크</div>
            <div className="text-sm font-bold text-slate-300">
              {schedulerStatus?.last_check_date || '-'}
            </div>
          </div>
        </div>

        {schedulerStatus?.crawling_error && (
          <div className="mt-4 p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl">
            <div className="flex items-center gap-2 text-rose-400 text-sm font-bold">
              <AlertCircle className="w-4 h-4" />
              {schedulerStatus.crawling_error}
            </div>
          </div>
        )}
      </div>

      {/* Real-time Progress Card (크롤링 중일 때만 표시) */}
      {isCrawling && schedulerStatus?.crawl_progress && (
        <div className={`bg-[#1a1f2e] border border-amber-500/50 rounded-2xl ${isMobile ? 'p-4' : 'p-6'} animate-pulse-slow`}>
          <div className="flex items-center justify-between mb-4">
            <h3 className={`${isMobile ? 'text-base' : 'text-lg'} font-bold text-white flex items-center gap-2`}>
              <Activity className={`${isMobile ? 'w-4 h-4' : 'w-5 h-5'} text-amber-400`} />
              실시간 수집 진행률
            </h3>
            <span className="text-xs text-amber-400 font-bold">
              {schedulerStatus.crawling_status?.toUpperCase()} 모드
            </span>
          </div>
          
          {/* Progress Bar */}
          <div className="mb-4">
            <div className="flex justify-between text-xs text-slate-400 mb-2">
              <span>
                {schedulerStatus.crawl_progress.current.toLocaleString()} / {schedulerStatus.crawl_progress.total.toLocaleString()} 종목
              </span>
              <span>
                {schedulerStatus.crawl_progress.total > 0 
                  ? ((schedulerStatus.crawl_progress.current / schedulerStatus.crawl_progress.total) * 100).toFixed(1)
                  : 0}%
              </span>
            </div>
            <div className="w-full h-3 bg-slate-700 rounded-full overflow-hidden">
              <div 
                className="h-full bg-gradient-to-r from-amber-500 to-amber-400 transition-all duration-300 ease-out"
                style={{ 
                  width: `${schedulerStatus.crawl_progress.total > 0 
                    ? (schedulerStatus.crawl_progress.current / schedulerStatus.crawl_progress.total) * 100 
                    : 0}%` 
                }}
              />
            </div>
          </div>
          
          {/* Stats Grid */}
          <div className={`grid ${isMobile ? 'grid-cols-2 gap-2' : 'grid-cols-4 gap-4'}`}>
            <div className="bg-[#0d1117] rounded-lg p-2">
              <div className="text-[10px] text-slate-500 uppercase">현재 종목</div>
              <div className="text-xs font-bold text-white truncate">
                {schedulerStatus.crawl_progress.current_name || schedulerStatus.crawl_progress.current_code || '-'}
              </div>
            </div>
            <div className="bg-[#0d1117] rounded-lg p-2">
              <div className="text-[10px] text-slate-500 uppercase">성공</div>
              <div className="text-xs font-bold text-emerald-400">
                {schedulerStatus.crawl_progress.success_count.toLocaleString()}
              </div>
            </div>
            <div className="bg-[#0d1117] rounded-lg p-2">
              <div className="text-[10px] text-slate-500 uppercase">실패</div>
              <div className="text-xs font-bold text-rose-400">
                {schedulerStatus.crawl_progress.fail_count.toLocaleString()}
              </div>
            </div>
            <div className="bg-[#0d1117] rounded-lg p-2">
              <div className="text-[10px] text-slate-500 uppercase">예상 남은 시간</div>
              <div className="text-xs font-bold text-slate-300">
                {schedulerStatus.crawl_progress.eta_seconds 
                  ? formatDuration(schedulerStatus.crawl_progress.eta_seconds)
                  : '계산 중...'}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Quick Actions */}
      <div className={`bg-[#1a1f2e] border border-slate-800 rounded-2xl ${isMobile ? 'p-4' : 'p-6'}`}>
        <h3 className={`${isMobile ? 'text-base' : 'text-lg'} font-bold text-white mb-4 flex items-center gap-2`}>
          <Play className={`${isMobile ? 'w-4 h-4' : 'w-5 h-5'} text-emerald-400`} />
          빠른 실행
        </h3>
        
        <div className={`flex ${isMobile ? 'flex-col gap-2' : 'gap-3'}`}>
          <button
            onClick={() => handleTriggerTask('eod')}
            disabled={isCrawling}
            className={`flex-1 flex items-center justify-center gap-2 ${isMobile ? 'py-2 text-xs' : 'py-3 text-sm'} rounded-xl font-bold transition-all ${
              isCrawling 
                ? 'bg-slate-700 text-slate-500 cursor-not-allowed' 
                : 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/20'
            }`}
          >
            <Play className="w-4 h-4" />
            EOD 수집
          </button>
          
          <button
            onClick={() => handleTriggerTask('intraday')}
            disabled={isCrawling}
            className={`flex-1 flex items-center justify-center gap-2 ${isMobile ? 'py-2 text-xs' : 'py-3 text-sm'} rounded-xl font-bold transition-all ${
              isCrawling 
                ? 'bg-slate-700 text-slate-500 cursor-not-allowed' 
                : 'bg-violet-500/10 border border-violet-500/30 text-violet-400 hover:bg-violet-500/20'
            }`}
          >
            <Play className="w-4 h-4" />
            Intraday 수집
          </button>
          
          <button
            onClick={() => handleTriggerTask('inference')}
            disabled={isCrawling}
            className={`flex-1 flex items-center justify-center gap-2 ${isMobile ? 'py-2 text-xs' : 'py-3 text-sm'} rounded-xl font-bold transition-all ${
              isCrawling 
                ? 'bg-slate-700 text-slate-500 cursor-not-allowed' 
                : 'bg-point-cyan/10 border border-point-cyan/30 text-point-cyan hover:bg-point-cyan/20'
            }`}
          >
            <Play className="w-4 h-4" />
            AI 예측
          </button>
        </div>
      </div>

      {/* Manual Crawl */}
      <div className={`bg-[#1a1f2e] border border-slate-800 rounded-2xl ${isMobile ? 'p-4' : 'p-6'}`}>
        <h3 className={`${isMobile ? 'text-base' : 'text-lg'} font-bold text-white mb-4 flex items-center gap-2`}>
          <Calendar className={`${isMobile ? 'w-4 h-4' : 'w-5 h-5'} text-amber-400`} />
          수동 수집
        </h3>
        
        <div className={`${isMobile ? 'space-y-3' : 'flex items-end gap-4'}`}>
          <div className={`${isMobile ? '' : 'flex-1'}`}>
            <label className="block text-xs text-slate-500 mb-1">시작 날짜</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full bg-[#0d1117] border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-point-cyan"
            />
          </div>
          
          <div className={`${isMobile ? '' : 'flex-1'}`}>
            <label className="block text-xs text-slate-500 mb-1">종료 날짜 (선택)</label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="w-full bg-[#0d1117] border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-point-cyan"
            />
          </div>
          
          <div className={`${isMobile ? '' : 'w-32'}`}>
            <label className="block text-xs text-slate-500 mb-1">모드</label>
            <select
              value={crawlMode}
              onChange={(e) => setCrawlMode(e.target.value as 'eod' | 'intraday')}
              className="w-full bg-[#0d1117] border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-point-cyan"
            >
              <option value="eod">EOD</option>
              <option value="intraday">Intraday</option>
            </select>
          </div>
          
          <button
            onClick={handleManualCrawl}
            disabled={isCrawling || isStartingCrawl || !startDate}
            className={`${isMobile ? 'w-full' : ''} flex items-center justify-center gap-2 px-6 py-2 rounded-lg font-bold transition-all ${
              (isCrawling || !startDate) 
                ? 'bg-slate-700 text-slate-500 cursor-not-allowed' 
                : 'bg-amber-500 text-black hover:bg-amber-400'
            }`}
          >
            {isStartingCrawl ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            수집 시작
          </button>
        </div>
      </div>

      {/* Last Crawl Info */}
      {schedulerStatus?.last_crawl_completed_at && (
        <div className={`bg-[#1a1f2e] border border-slate-800 rounded-2xl ${isMobile ? 'p-4' : 'p-6'}`}>
          <h3 className={`${isMobile ? 'text-base' : 'text-lg'} font-bold text-white mb-4 flex items-center gap-2`}>
            <Clock className={`${isMobile ? 'w-4 h-4' : 'w-5 h-5'} text-slate-400`} />
            최근 수집 정보
          </h3>
          
          <div className={`grid ${isMobile ? 'grid-cols-2 gap-3' : 'grid-cols-4 gap-4'}`}>
            <div>
              <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">완료 시각</div>
              <div className="text-sm font-bold text-slate-300">{formatDateTime(schedulerStatus.last_crawl_completed_at)}</div>
            </div>
            <div>
              <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">모드</div>
              <div className="text-sm font-bold text-slate-300">{schedulerStatus.last_crawl_mode || '-'}</div>
            </div>
            <div>
              <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">날짜 범위</div>
              <div className="text-sm font-bold text-slate-300">{schedulerStatus.last_crawl_date_range || '-'}</div>
            </div>
            <div>
              <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">소요 시간</div>
              <div className="text-sm font-bold text-slate-300">{formatDuration(schedulerStatus.last_crawl_duration)}</div>
            </div>
          </div>
        </div>
      )}

      {/* Recent Collected Dates */}
      <div className={`bg-[#1a1f2e] border border-slate-800 rounded-2xl ${isMobile ? 'p-4' : 'p-6'}`}>
        <h3 className={`${isMobile ? 'text-base' : 'text-lg'} font-bold text-white mb-4 flex items-center gap-2`}>
          <FolderOpen className={`${isMobile ? 'w-4 h-4' : 'w-5 h-5'} text-point-cyan`} />
          최근 수집된 날짜 (최근 30일)
        </h3>
        
        {isLoadingDates ? (
          <div className="flex items-center justify-center py-8 text-slate-500">
            <Loader2 className="w-5 h-5 animate-spin mr-2" />
            로딩 중...
          </div>
        ) : crawlDates.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {crawlDates.map((dateInfo) => (
              <span
                key={dateInfo.date}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold ${
                  dateInfo.hasData
                    ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                    : 'bg-slate-700/50 text-slate-500 border border-slate-600'
                }`}
              >
                {dateInfo.date}
              </span>
            ))}
          </div>
        ) : (
          <div className="text-center py-8 text-slate-500 text-sm">
            수집된 데이터가 없습니다.
          </div>
        )}
      </div>
    </div>
  );
};

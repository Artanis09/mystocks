"""
자동매매 전략 1: 상한가 갭상승 모멘텀 (Strategy 1 - Upper Limit Gap Momentum)

목표: 전일 상한가 종목을 대상으로 당일 시초 갭 조건을 만족할 경우 자동 진입하고,
      TP/SL/EOD 규칙으로 청산하는 안정적인 자동매매 시스템

전략 파라미터:
- Setup: 전일 종가 기준 상한가 도달(수익률 ≥ 29.5%), 시가총액 ≥ 500억
- Entry: 당일 시가가 전일 종가 대비 +2% 이상 갭상승 시 매수
- TP: +10%
- SL: -3%
- EOD: 장 마감 전 전량 청산
"""

import os
import json
import time
import sqlite3
import threading
import logging
from datetime import datetime, timedelta, date
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from pathlib import Path
import requests
import pandas as pd

# =============================
# 로깅 설정
# =============================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('auto_trading.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# =============================
# ntfy 알림 설정
# =============================
NTFY_TOPIC_URL = "https://ntfy.sh/wayne-akdlrjf0924-auto1"


def send_ntfy_notification(title: str, message: str, priority: str = "default", tags: List[str] = None):
    """ntfy.sh로 알림 전송"""
    try:
        headers = {
            "Title": title,
            "Priority": priority,
        }
        if tags:
            headers["Tags"] = ",".join(tags)
        
        response = requests.post(
            NTFY_TOPIC_URL,
            data=message.encode('utf-8'),
            headers=headers,
            timeout=5
        )
        if response.status_code == 200:
            logger.info(f"[NTFY] 알림 전송 성공: {title}")
        else:
            logger.warning(f"[NTFY] 알림 전송 실패: {response.status_code}")
    except Exception as e:
        logger.error(f"[NTFY] 알림 전송 오류: {e}")


# =============================
# 휴장일 체크 유틸리티
# =============================
def get_korean_holidays(year: int) -> set:
    """한국 주식시장 휴장일 목록 반환 (공휴일 + 추가 휴장일)"""
    # 고정 공휴일
    holidays = {
        f"{year}-01-01",  # 신정
        f"{year}-03-01",  # 삼일절
        f"{year}-05-05",  # 어린이날
        f"{year}-06-06",  # 현충일
        f"{year}-08-15",  # 광복절
        f"{year}-10-03",  # 개천절
        f"{year}-10-09",  # 한글날
        f"{year}-12-25",  # 크리스마스
        f"{year}-12-31",  # 연말
    }
    
    # 2026년 음력 공휴일 (추정)
    if year == 2026:
        holidays.update([
            "2026-01-28", "2026-01-29", "2026-01-30",  # 설날 연휴
            "2026-02-17",  # 대체공휴일 (설날)
            "2026-05-24",  # 부처님오신날
            "2026-10-04", "2026-10-05", "2026-10-06",  # 추석 연휴
        ])
    elif year == 2025:
        holidays.update([
            "2025-01-28", "2025-01-29", "2025-01-30",  # 설날 연휴
            "2025-05-05",  # 부처님오신날
            "2025-10-05", "2025-10-06", "2025-10-07",  # 추석 연휴
        ])
    
    return holidays


def is_trading_day(check_date: date = None) -> bool:
    """거래일 여부 확인 (주말 및 휴장일 체크)"""
    if check_date is None:
        check_date = date.today()
    
    # 주말 체크
    if check_date.weekday() >= 5:  # 토(5), 일(6)
        return False
    
    # 휴장일 체크
    holidays = get_korean_holidays(check_date.year)
    if check_date.strftime('%Y-%m-%d') in holidays:
        return False
    
    return True


def get_prev_trading_day(from_date: date = None) -> date:
    """이전 거래일 반환"""
    if from_date is None:
        from_date = date.today()
    
    prev_day = from_date - timedelta(days=1)
    while not is_trading_day(prev_day):
        prev_day -= timedelta(days=1)
    
    return prev_day


# =============================
# 전략 상수
# =============================
class StrategyConfig:
    """전략 파라미터 설정"""
    # Setup 조건 (유니버스 필터)
    UPPER_LIMIT_RATE = 29.5      # 상한가 기준 수익률 (%)
    MIN_MARKET_CAP = 1000        # 최소 시가총액 (억원) - 1,000억 이상
    MIN_TRADING_VALUE = 300      # 최소 거래대금 (억원) - 300억 이상
    
    # Entry 조건 (진입)
    GAP_THRESHOLD_MIN = 2.0      # 갭상승 최소 기준 (%) - 시가 +2% 이상
    GAP_THRESHOLD_MAX = 5.0      # 갭상승 최대 기준 (%) - 시가 +5% 이하
    ENTRY_AT_PREV_CLOSE = True   # 전일종가(0%) 도달 시 매수
    GAP_CONFIRM_COUNT = 2        # 갭 확인 횟수 (노이즈 제거)
    ENTRY_START_TIME = "09:00"   # 진입 시작 시간
    ENTRY_END_TIME = "15:20"     # 진입 종료 시간 (종가 매도 전까지)
    USE_LIMIT_ORDER_AT_OPEN = False  # 시가 지정가 대신 전일종가 지정가 사용
    USE_LIMIT_ORDER_AT_PREV_CLOSE = True  # 전일종가 지정가 주문 (AI예측 모드용)
    ENTRY_CANCEL_TIME = "09:30"  # 미체결 취소 시간 (9:30까지 미체결 시 취소)
    
    # 시장 필터
    USE_MARKET_FILTER = True     # KOSPI 5일선 필터 사용 여부
    MARKET_MA_DAYS = 5           # KOSPI 이평선 기간
    
    # Exit 조건 (청산)
    TAKE_PROFIT_RATE = 10.0      # 익절 기준 (%)
    STOP_LOSS_RATE = -4.0        # 손절 기준 (%) - 진입가 대비 -4%
    EOD_SELL_START = "15:20"     # EOD 청산 시작
    EOD_SELL_END = "15:28"       # EOD 청산 종료
    
    # 리스크 관리
    MAX_DAILY_LOSS_RATE = -5.0   # 일일 최대 손실률 (%)
    MAX_POSITIONS = 5            # 최대 동시 보유 종목 수 (투자비율 = 1/N)
    
    # 주문 설정
    ORDER_SLIPPAGE_TICKS = 2     # 슬리피지 허용 틱수
    ORDER_TIMEOUT_SEC = 5        # 주문 타임아웃 (초)
    ORDER_RETRY_COUNT = 3        # 주문 재시도 횟수
    ORDER_RETRY_DELAY = 0.5      # 재시도 딜레이 (초)
    
    # 진입 실패 판정
    ENTRY_MAX_RISE_RATE = 8.0    # 진입 포기 급등 기준 (전일종가 대비 %) - 너무 올랐으면 진입 포기
    ENTRY_PENDING_TIMEOUT = 60   # 미체결 대기 타임아웃 (초) - 초과 시 주문 취소
    ENTRY_ORDER_CANCEL_AFTER_WINDOW = True  # 진입 윈도우 종료 후 미체결 취소


# =============================
# 상태 머신 정의
# =============================
class PositionState(Enum):
    """종목별 전략 상태"""
    IDLE = "IDLE"                   # 미활성 상태
    WATCHING = "WATCHING"           # 감시 중 (유니버스에 포함됨, 갭조건 충족)
    ENTRY_PENDING = "ENTRY_PENDING" # 진입 주문 대기/접수
    ENTERED = "ENTERED"             # 보유 중
    EXIT_PENDING = "EXIT_PENDING"   # 청산 주문 대기/접수
    CLOSED = "CLOSED"               # 청산 완료
    SKIPPED = "SKIPPED"             # 건너뜀 (조건 미충족, 오류 등)
    DISQUALIFIED = "DISQUALIFIED"   # 탈락 (갭 조건 미충족, 감시 제외)
    ERROR = "ERROR"                 # 오류 상태


class StrategyPhase(Enum):
    """전략 실행 단계"""
    IDLE = "IDLE"                   # 비활성 (장외 시간)
    PREPARING = "PREPARING"         # 준비 중 (08:40~08:59)
    ENTRY_WINDOW = "ENTRY_WINDOW"   # 진입 구간 (09:00~09:03)
    MONITORING = "MONITORING"       # 장중 모니터링 (09:03~15:20)
    EOD_CLOSING = "EOD_CLOSING"     # EOD 청산 (15:20~15:28)
    CLOSED = "CLOSED"               # 장 종료


# =============================
# 데이터 클래스 정의
# =============================
@dataclass
class UniverseStock:
    """유니버스 종목 정보"""
    code: str
    name: str
    prev_close: float           # 전일 종가
    prev_high: float            # 전일 고가
    change_rate: float          # 전일 등락률
    market_cap: float           # 시가총액 (억원)
    added_date: str             # 유니버스 편입일


@dataclass
class Position:
    """포지션 (보유/감시 종목) 정보"""
    code: str
    name: str
    state: PositionState = PositionState.IDLE
    
    # 가격 정보
    prev_close: float = 0.0     # 전일 종가
    prev_high: float = 0.0      # 전일 고가
    open_price: float = 0.0     # 당일 시가
    entry_price: float = 0.0    # 진입가
    current_price: float = 0.0  # 현재가
    quantity: int = 0           # 보유 수량
    
    # 손익 정보
    unrealized_pnl: float = 0.0       # 미실현 손익
    unrealized_pnl_rate: float = 0.0  # 미실현 손익률
    
    # 주문 정보
    order_id: str = ""          # 최근 주문번호
    pending_quantity: int = 0   # 미체결 수량
    order_time: str = ""        # 주문 시간 (미체결 타임아웃 체크용)
    limit_order_price: float = 0.0  # 지정가 주문 가격 (시가 지정가)
    market_cap: float = 0.0     # 시가총액 (억원)
    
    # 이벤트 정보
    gap_confirms: int = 0       # 갭 확인 횟수
    entry_time: str = ""        # 진입 시간
    exit_time: str = ""         # 청산 시간
    exit_reason: str = ""       # 청산 사유 (TP/SL/EOD/MANUAL)
    
    # 오류 정보
    error_message: str = ""
    retry_count: int = 0
    
    def to_dict(self) -> dict:
        """딕셔너리 변환"""
        return {
            'code': self.code,
            'name': self.name,
            'state': self.state.value,
            'prev_close': self.prev_close,
            'open_price': self.open_price,
            'entry_price': self.entry_price,
            'current_price': self.current_price,
            'quantity': self.quantity,
            'unrealized_pnl': self.unrealized_pnl,
            'unrealized_pnl_rate': self.unrealized_pnl_rate,
            'order_id': self.order_id,
            'pending_quantity': self.pending_quantity,
            'order_time': self.order_time,
            'market_cap': self.market_cap,
            'gap_confirms': self.gap_confirms,
            'entry_time': self.entry_time,
            'exit_time': self.exit_time,
            'exit_reason': self.exit_reason,
            'error_message': self.error_message,
            'retry_count': self.retry_count
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Position':
        """딕셔너리에서 생성"""
        pos = cls(code=data['code'], name=data['name'])
        pos.state = PositionState(data.get('state', 'IDLE'))
        pos.prev_close = data.get('prev_close', 0.0)
        pos.open_price = data.get('open_price', 0.0)
        pos.entry_price = data.get('entry_price', 0.0)
        pos.current_price = data.get('current_price', 0.0)
        pos.quantity = data.get('quantity', 0)
        pos.unrealized_pnl = data.get('unrealized_pnl', 0.0)
        pos.unrealized_pnl_rate = data.get('unrealized_pnl_rate', 0.0)
        pos.order_id = data.get('order_id', '')
        pos.pending_quantity = data.get('pending_quantity', 0)
        pos.order_time = data.get('order_time', '')
        pos.market_cap = data.get('market_cap', 0.0)
        pos.gap_confirms = data.get('gap_confirms', 0)
        pos.entry_time = data.get('entry_time', '')
        pos.exit_time = data.get('exit_time', '')
        pos.exit_reason = data.get('exit_reason', '')
        pos.error_message = data.get('error_message', '')
        pos.retry_count = data.get('retry_count', 0)
        return pos


@dataclass
class StrategyState:
    """전략 전체 상태"""
    is_running: bool = False
    phase: StrategyPhase = StrategyPhase.IDLE
    today: str = ""
    
    # 계좌 정보
    total_asset: float = 0.0
    available_cash: float = 0.0
    daily_pnl: float = 0.0
    daily_pnl_rate: float = 0.0
    
    # 유니버스
    universe: List[UniverseStock] = field(default_factory=list)
    
    # 포지션
    positions: Dict[str, Position] = field(default_factory=dict)
    
    # 통계
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    
    # 로그
    logs: List[dict] = field(default_factory=list)
    
    # 마지막 업데이트
    last_update: str = ""
    
    def to_dict(self) -> dict:
        """딕셔너리 변환"""
        return {
            'is_running': self.is_running,
            'phase': self.phase.value,
            'today': self.today,
            'total_asset': self.total_asset,
            'available_cash': self.available_cash,
            'daily_pnl': self.daily_pnl,
            'daily_pnl_rate': self.daily_pnl_rate,
            'universe': [asdict(u) for u in self.universe],
            'positions': {k: v.to_dict() for k, v in self.positions.items()},
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'logs': self.logs[-100:],  # 최근 100개만
            'last_update': self.last_update
        }


# =============================
# 자동매매 엔진
# =============================
class AutoTradingEngine:
    """자동매매 전략 실행 엔진"""
    
    def __init__(self, db_path: str = "mystock.db", is_mock: bool = True):
        self.db_path = db_path
        self.state = StrategyState()
        self.config = StrategyConfig()
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        # 모의투자/실전투자 모드
        self.is_mock = is_mock
        
        # KIS API 설정 (모의/실전에 따라 다른 키 사용)
        if is_mock:
            self.kis_base_url = "https://openapivts.koreainvestment.com:29443"  # 모의투자 URL
            self.app_key = os.getenv("KIS_APP_KEY", "")
            self.app_secret = os.getenv("KIS_APP_SECRET", "")
            self.account_no = os.getenv("KIS_ACCOUNT_NO", "")
        else:
            self.kis_base_url = "https://openapi.koreainvestment.com:9443"  # 실전투자 URL
            self.app_key = os.getenv("KIS_REAL_APP_KEY", os.getenv("KIS_APP_KEY", ""))
            self.app_secret = os.getenv("KIS_REAL_APP_SECRET", os.getenv("KIS_APP_SECRET", ""))
            self.account_no = os.getenv("KIS_REAL_ACCOUNT_NO", os.getenv("KIS_ACCOUNT_NO", ""))
        
        self._access_token: Optional[str] = None
        self._token_expired: float = 0
        
        # 상태 파일 (모의/실전 분리)
        mode_suffix = "_mock" if is_mock else "_real"
        self.state_file = Path(f"auto_trading_state{mode_suffix}.json")
        
        # 초기화
        self._init_db()
        self._load_state()
    
    def _init_db(self):
        """데이터베이스 초기화"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 자동매매 로그 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auto_trading_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    date TEXT NOT NULL,
                    level TEXT NOT NULL,
                    phase TEXT,
                    code TEXT,
                    event TEXT NOT NULL,
                    message TEXT,
                    data TEXT
                )
            """)
            
            # 자동매매 거래 내역 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auto_trading_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_date TEXT NOT NULL,
                    code TEXT NOT NULL,
                    name TEXT NOT NULL,
                    trade_type TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    price REAL NOT NULL,
                    amount REAL NOT NULL,
                    exit_reason TEXT,
                    pnl REAL,
                    pnl_rate REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 유니버스 히스토리 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auto_trading_universe (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    code TEXT NOT NULL,
                    name TEXT NOT NULL,
                    prev_close REAL,
                    change_rate REAL,
                    market_cap REAL,
                    result TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(date, code)
                )
            """)
            
            conn.commit()
            conn.close()
            logger.info("자동매매 DB 초기화 완료")
        except Exception as e:
            logger.error(f"DB 초기화 실패: {e}")
    
    def _save_state(self):
        """상태 저장"""
        try:
            with self._lock:
                with open(self.state_file, 'w', encoding='utf-8') as f:
                    json.dump(self.state.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"상태 저장 실패: {e}")
    
    def _load_state(self):
        """상태 로드"""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                # 오늘 날짜 확인
                today = datetime.now().strftime('%Y-%m-%d')
                if data.get('today') != today:
                    # 날짜가 다르면 새로운 상태로 시작
                    logger.info(f"새로운 거래일: {today}")
                    self.state = StrategyState()
                    self.state.today = today
                else:
                    # 같은 날이면 상태 복원
                    self.state.is_running = data.get('is_running', False)
                    self.state.phase = StrategyPhase(data.get('phase', 'IDLE'))
                    self.state.today = data.get('today', today)
                    self.state.total_asset = data.get('total_asset', 0.0)
                    self.state.available_cash = data.get('available_cash', 0.0)
                    self.state.daily_pnl = data.get('daily_pnl', 0.0)
                    self.state.daily_pnl_rate = data.get('daily_pnl_rate', 0.0)
                    self.state.total_trades = data.get('total_trades', 0)
                    self.state.winning_trades = data.get('winning_trades', 0)
                    self.state.losing_trades = data.get('losing_trades', 0)
                    
                    # 유니버스 복원
                    self.state.universe = [
                        UniverseStock(**u) for u in data.get('universe', [])
                    ]
                    
                    # 포지션 복원
                    for code, pos_data in data.get('positions', {}).items():
                        self.state.positions[code] = Position.from_dict(pos_data)
                    
                    logger.info(f"상태 복원 완료: {len(self.state.positions)}개 포지션")
            else:
                self.state.today = datetime.now().strftime('%Y-%m-%d')
        except Exception as e:
            logger.error(f"상태 로드 실패: {e}")
            self.state = StrategyState()
            self.state.today = datetime.now().strftime('%Y-%m-%d')
    
    def _log_event(self, level: str, event: str, message: str, 
                   code: str = "", data: dict = None):
        """이벤트 로그 기록"""
        timestamp = datetime.now().isoformat()
        log_entry = {
            'timestamp': timestamp,
            'level': level,
            'event': event,
            'code': code,
            'message': message,
            'data': data
        }
        
        # 메모리 로그
        with self._lock:
            self.state.logs.append(log_entry)
            if len(self.state.logs) > 500:
                self.state.logs = self.state.logs[-500:]
        
        # DB 로그
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO auto_trading_logs 
                (timestamp, date, level, phase, code, event, message, data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                timestamp,
                self.state.today,
                level,
                self.state.phase.value,
                code,
                event,
                message,
                json.dumps(data) if data else None
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"로그 DB 저장 실패: {e}")
        
        # 콘솔 로그
        log_msg = f"[{event}] {code}: {message}" if code else f"[{event}] {message}"
        if level == 'ERROR':
            logger.error(log_msg)
        elif level == 'WARNING':
            logger.warning(log_msg)
        else:
            logger.info(log_msg)
    
    # =============================
    # KIS API 연동
    # =============================
    
    def _get_access_token(self) -> Optional[str]:
        """KIS 액세스 토큰 조회/발급"""
        try:
            # 캐시된 토큰이 유효하면 반환
            if self._access_token and time.time() < self._token_expired - 600:
                return self._access_token
            
            # 파일에서 토큰 로드 (모의/실전 분리)
            token_suffix = "_mock" if self.is_mock else "_real"
            token_file = Path(f"kis_token{token_suffix}.json")
            if token_file.exists():
                with open(token_file, 'r') as f:
                    token_data = json.load(f)
                    if time.time() < token_data.get('expired_time', 0) - 600:
                        self._access_token = token_data['access_token']
                        self._token_expired = token_data['expired_time']
                        return self._access_token
            
            # 새 토큰 발급
            url = f"{self.kis_base_url}/oauth2/tokenP"
            response = requests.post(url, json={
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "appsecret": self.app_secret
            }, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                self._access_token = data['access_token']
                self._token_expired = time.time() + data.get('expires_in', 86400)
                
                # 토큰 저장 (모의/실전 분리)
                with open(token_file, 'w') as f:
                    json.dump({
                        'access_token': self._access_token,
                        'expired_time': self._token_expired
                    }, f)
                
                self._log_event('INFO', 'TOKEN_ISSUED', '토큰 발급 성공')
                return self._access_token
            else:
                self._log_event('ERROR', 'TOKEN_FAILED', f'토큰 발급 실패: {response.status_code}')
                return None
        except Exception as e:
            self._log_event('ERROR', 'TOKEN_ERROR', f'토큰 오류: {e}')
            return None
    
    def _call_kis_api(self, endpoint: str, params: dict = None, 
                      tr_id: str = "", method: str = "GET", 
                      body: dict = None) -> dict:
        """KIS API 호출"""
        token = self._get_access_token()
        if not token:
            return {'error': '토큰 없음'}
        
        url = f"{self.kis_base_url}{endpoint}"
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P"
        }
        
        try:
            if method == "POST":
                response = requests.post(url, headers=headers, json=body, timeout=10)
            else:
                response = requests.get(url, headers=headers, params=params, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code in (401, 403):
                # 토큰 만료 - 재발급 시도
                self._access_token = None
                self._log_event('WARNING', 'TOKEN_EXPIRED', '토큰 만료, 재발급 시도')
                return self._call_kis_api(endpoint, params, tr_id, method, body)
            else:
                return {'error': f'API 오류: {response.status_code}', 'detail': response.text}
        except Exception as e:
            return {'error': str(e)}
    
    def _get_current_price(self, code: str) -> dict:
        """현재가 조회"""
        result = self._call_kis_api(
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            params={"fid_cond_mrkt_div_code": "J", "fid_input_iscd": code.zfill(6)},
            tr_id="FHKST01010100"
        )
        
        output = result.get('output', {})
        if output:
            return {
                'current_price': int(output.get('stck_prpr', 0) or 0),
                'open_price': int(output.get('stck_oprc', 0) or 0),
                'high_price': int(output.get('stck_hgpr', 0) or 0),
                'low_price': int(output.get('stck_lwpr', 0) or 0),
                'prev_close': int(output.get('stck_sdpr', 0) or 0),
                'change_rate': float(output.get('prdy_ctrt', 0) or 0),
                'volume': int(output.get('acml_vol', 0) or 0),
                'ask_price': int(output.get('askp1', 0) or 0),
                'bid_price': int(output.get('bidp1', 0) or 0)
            }
        return {}
    
    def _get_market_cap(self, code: str) -> float:
        """시가총액 조회 (억원 단위)
        
        KIS API: 주식기본조회 (FHKST01010100)의 hts_avls(시가총액) 필드 사용
        """
        try:
            result = self._call_kis_api(
                "/uapi/domestic-stock/v1/quotations/inquire-price",
                params={"fid_cond_mrkt_div_code": "J", "fid_input_iscd": code.zfill(6)},
                tr_id="FHKST01010100"
            )
            
            output = result.get('output', {})
            if output:
                # hts_avls: 시가총액 (억원 단위)
                market_cap_str = output.get('hts_avls', '0')
                market_cap = float(market_cap_str.replace(',', '') if market_cap_str else 0)
                return market_cap
            return 0.0
        except Exception as e:
            self._log_event('WARNING', 'MARKET_CAP_ERROR', f'시가총액 조회 실패: {e}', code=code)
            return 0.0
    
    def _get_account_balance(self) -> dict:
        """계좌 잔고 조회"""
        if not self.account_no:
            return {'error': '계좌번호 미설정'}
        
        parts = self.account_no.split('-')
        if len(parts) != 2:
            return {'error': '계좌번호 형식 오류'}
        
        result = self._call_kis_api(
            "/uapi/domestic-stock/v1/trading/inquire-balance",
            params={
                "CANO": parts[0],
                "ACNT_PRDT_CD": parts[1],
                "AFHR_FLPR_YN": "N",
                "OFL_YN": "",
                "INQR_DVSN": "02",
                "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "00",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": ""
            },
            tr_id=self._get_tr_id("TTTC8434R")
        )
        
        output1 = result.get('output1', [])  # 보유종목
        output2 = result.get('output2', [{}])[0] if result.get('output2') else {}
        
        holdings = {}
        for item in output1:
            code = item.get('pdno', '')
            if code:
                holdings[code] = {
                    'name': item.get('prdt_name', ''),
                    'quantity': int(item.get('hldg_qty', 0) or 0),
                    'avg_price': float(item.get('pchs_avg_pric', 0) or 0),
                    'current_price': int(item.get('prpr', 0) or 0),
                    'eval_amount': int(item.get('evlu_amt', 0) or 0),
                    'profit_loss': int(item.get('evlu_pfls_amt', 0) or 0),
                    'profit_rate': float(item.get('evlu_pfls_rt', 0) or 0)
                }
        
        return {
            'holdings': holdings,
            'total_eval': int(output2.get('tot_evlu_amt', 0) or 0),
            'total_purchase': int(output2.get('pchs_amt_smtl_amt', 0) or 0),
            'total_pnl': int(output2.get('evlu_pfls_smtl_amt', 0) or 0),
            'deposit': int(output2.get('dnca_tot_amt', 0) or 0),
            'available': int(output2.get('nass_amt', 0) or 0)
        }
    
    def _get_tr_id(self, base_tr_id: str) -> str:
        """모의/실전투자에 맞는 TR ID 반환
        모의투자: T -> V로 변경 (예: TTTC0802U -> VTTC0802U)
        """
        if self.is_mock and base_tr_id.startswith('T'):
            return 'V' + base_tr_id[1:]
        return base_tr_id
    
    def _place_order(self, code: str, quantity: int, order_type: str, 
                     price: int = 0) -> dict:
        """주문 실행
        order_type: 'buy' or 'sell'
        price: 0이면 시장가, 양수면 지정가
        """
        if not self.account_no:
            return {'error': '계좌번호 미설정'}
        
        parts = self.account_no.split('-')
        
        # 주문 구분: 01(시장가), 00(지정가)
        ord_dvsn = "01" if price == 0 else "00"
        
        body = {
            "CANO": parts[0],
            "ACNT_PRDT_CD": parts[1],
            "PDNO": code.zfill(6),
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(quantity),
            "ORD_UNPR": str(price)
        }
        
        # TR_ID: 매수(TTTC0802U), 매도(TTTC0801U) - 모의투자는 V로 시작
        base_tr_id = "TTTC0802U" if order_type == "buy" else "TTTC0801U"
        tr_id = self._get_tr_id(base_tr_id)
        
        result = self._call_kis_api(
            "/uapi/domestic-stock/v1/trading/order-cash",
            tr_id=tr_id,
            method="POST",
            body=body
        )
        
        if 'error' in result:
            return result
        
        output = result.get('output', {})
        return {
            'success': True,
            'order_no': output.get('ODNO', ''),
            'order_time': output.get('ORD_TMD', ''),
            'code': code,
            'quantity': quantity,
            'order_type': order_type
        }
    
    def _get_order_status(self, order_no: str) -> dict:
        """주문 체결 상태 조회"""
        if not self.account_no:
            return {'error': '계좌번호 미설정'}
        
        parts = self.account_no.split('-')
        today = datetime.now().strftime('%Y%m%d')
        
        result = self._call_kis_api(
            "/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
            params={
                "CANO": parts[0],
                "ACNT_PRDT_CD": parts[1],
                "INQR_STRT_DT": today,
                "INQR_END_DT": today,
                "SLL_BUY_DVSN_CD": "00",  # 전체
                "INQR_DVSN": "00",
                "PDNO": "",
                "CCLD_DVSN": "00",
                "ORD_GNO_BRNO": "",
                "ODNO": order_no,
                "INQR_DVSN_3": "00",
                "INQR_DVSN_1": "",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": ""
            },
            tr_id=self._get_tr_id("TTTC8001R")
        )
        
        output1 = result.get('output1', [])
        for item in output1:
            if item.get('odno') == order_no:
                return {
                    'order_no': order_no,
                    'code': item.get('pdno', ''),
                    'order_qty': int(item.get('ord_qty', 0) or 0),
                    'exec_qty': int(item.get('tot_ccld_qty', 0) or 0),
                    'exec_price': float(item.get('avg_prvs', 0) or 0),
                    'remain_qty': int(item.get('rmn_qty', 0) or 0),
                    'status': 'FILLED' if int(item.get('rmn_qty', 0) or 0) == 0 else 'PARTIAL'
                }
        
        return {'error': '주문 조회 실패'}
    
    def _cancel_order(self, order_no: str, code: str, quantity: int) -> dict:
        """미체결 주문 취소
        
        Args:
            order_no: 원주문번호
            code: 종목코드
            quantity: 취소할 수량
        """
        if not self.account_no or not order_no:
            return {'error': '계좌번호 또는 주문번호 없음'}
        
        parts = self.account_no.split('-')
        
        body = {
            "CANO": parts[0],
            "ACNT_PRDT_CD": parts[1],
            "KRX_FWDG_ORD_ORGNO": "",  # 거래소 주문조직번호 (공백)
            "ORGN_ODNO": order_no,      # 원주문번호
            "ORD_DVSN": "00",           # 지정가
            "RVSE_CNCL_DVSN_CD": "02",  # 취소
            "ORD_QTY": str(quantity),
            "ORD_UNPR": "0",
            "QTY_ALL_ORD_YN": "Y"       # 전량 취소
        }
        
        # TR_ID: 주문취소 (모의: VTTC0803U, 실전: TTTC0803U)
        tr_id = self._get_tr_id("TTTC0803U")
        
        result = self._call_kis_api(
            "/uapi/domestic-stock/v1/trading/order-rvsecncl",
            tr_id=tr_id,
            method="POST",
            body=body
        )
        
        if 'error' in result:
            return result
        
        output = result.get('output', {})
        return {
            'success': True,
            'order_no': output.get('ODNO', ''),
            'message': '주문 취소 완료'
        }
    
    def _check_market_filter(self) -> bool:
        """KOSPI 시장 필터: 지수가 5일 이평선 위에 있는지 확인
        
        Returns:
            True: 진입 허용 (KOSPI > 5일선)
            False: 진입 금지 (KOSPI < 5일선)
        """
        try:
            # KOSPI 지수 코드
            kospi_code = "0001"  # KIS API KOSPI 지수 코드
            
            # KIS API로 KOSPI 현재가 조회
            from kis_api import get_domestic_stock_price
            
            price_data = get_domestic_stock_price(kospi_code, is_mock=self.is_mock)
            if 'error' in price_data:
                # API 오류 시 진입 허용 (보수적 접근 대신 기회 제공)
                self._log_event('WARNING', 'MARKET_FILTER_ERROR', 
                              f'KOSPI 조회 실패, 필터 통과 처리: {price_data.get("error")}')
                return True
            
            current_kospi = price_data.get('current_price', 0)
            
            # pykrx로 5일 이평선 계산
            try:
                from pykrx import stock
                from datetime import timedelta
                
                end_date = datetime.now().strftime('%Y%m%d')
                start_date = (datetime.now() - timedelta(days=14)).strftime('%Y%m%d')
                
                kospi_df = stock.get_index_ohlcv_by_date(start_date, end_date, "1001")
                if not kospi_df.empty and len(kospi_df) >= self.config.MARKET_MA_DAYS:
                    ma5 = kospi_df['종가'].tail(self.config.MARKET_MA_DAYS).mean()
                    
                    if current_kospi > ma5:
                        self._log_event('INFO', 'MARKET_FILTER_PASS', 
                                      f'KOSPI {current_kospi:.2f} > 5일선 {ma5:.2f}')
                        return True
                    else:
                        self._log_event('INFO', 'MARKET_FILTER_FAIL', 
                                      f'KOSPI {current_kospi:.2f} < 5일선 {ma5:.2f}')
                        return False
            except Exception as e:
                self._log_event('WARNING', 'MARKET_MA_ERROR', f'5일선 계산 실패: {e}')
                return True  # 계산 실패 시 진입 허용
            
            return True
            
        except Exception as e:
            self._log_event('ERROR', 'MARKET_FILTER_EXCEPTION', f'시장 필터 오류: {e}')
            return True  # 오류 시 진입 허용
    
    def _check_pending_timeout(self, position: Position) -> bool:
        """미체결 주문 타임아웃 체크 (15:20 경과 시 취소)
        
        Returns:
            True: 타임아웃 발생 (취소 필요)
            False: 정상 대기 중
        """
        now = datetime.now()
        
        # ENTRY_END_TIME 이후면 미체결 취소
        entry_end = datetime.strptime(
            f"{now.strftime('%Y-%m-%d')} {self.config.ENTRY_END_TIME}", 
            '%Y-%m-%d %H:%M'
        )
        
        if now >= entry_end:
            self._log_event('INFO', 'PENDING_TIMEOUT', 
                          f'진입 종료 시간({self.config.ENTRY_END_TIME}) 경과, 미체결 취소',
                          code=position.code)
            return True
        
        return False
    
    def _check_gap_disqualification(self, position: Position) -> bool:
        """갭 조건 미충족 시 탈락 처리
        
        장 시작 후 시가(open_price)가 전일종가 대비 +2%~+5% 범위가 아니면 탈락
        탈락된 종목은 DISQUALIFIED 상태로 변경되어 이후 감시에서 제외됨
        
        Returns:
            True: 탈락 (갭 조건 미충족)
            False: 통과 (갭 조건 충족, 계속 감시)
        """
        try:
            # 현재가 및 시가 조회
            price_data = self._get_current_price(position.code)
            if not price_data:
                self._log_event('WARNING', 'GAP_CHECK_FAIL', 
                              f'{position.name}: 가격 조회 실패, 탈락 처리',
                              code=position.code)
                position.state = PositionState.DISQUALIFIED
                position.error_message = '가격 조회 실패'
                return True
            
            open_price = price_data.get('open_price', 0)
            prev_close = position.prev_close
            
            if prev_close <= 0 or open_price <= 0:
                self._log_event('WARNING', 'GAP_CHECK_INVALID', 
                              f'{position.name}: 유효하지 않은 가격 (시가:{open_price}, 전일종가:{prev_close})',
                              code=position.code)
                position.state = PositionState.DISQUALIFIED
                position.error_message = '유효하지 않은 가격'
                return True
            
            # 갭률 계산 (시가 기준)
            gap_rate = (open_price - prev_close) / prev_close * 100
            
            # 갭 조건 확인: 시가가 전일종가 대비 +2% ~ +5% 범위
            gap_min = self.config.GAP_THRESHOLD_MIN
            gap_max = self.config.GAP_THRESHOLD_MAX
            
            if gap_min <= gap_rate <= gap_max:
                # 갭 조건 충족 - 계속 감시
                position.current_price = price_data.get('current_price', open_price)
                position.open_price = open_price  # 시가 저장
                self._log_event('INFO', 'GAP_QUALIFIED', 
                              f'{position.name}: 갭 조건 충족 (갭률: {gap_rate:.2f}%, 범위: {gap_min}%~{gap_max}%)',
                              code=position.code,
                              data={'gap_rate': gap_rate, 'open_price': open_price, 'prev_close': prev_close})
                return False  # 통과
            elif gap_rate < gap_min:
                # 갭 부족 - 탈락
                position.state = PositionState.DISQUALIFIED
                position.error_message = f'갭 부족 ({gap_rate:.2f}% < {gap_min}%)'
                self._log_event('INFO', 'GAP_DISQUALIFIED', 
                              f'{position.name}: 갭 부족으로 탈락 (갭률: {gap_rate:.2f}% < {gap_min}%)',
                              code=position.code,
                              data={'gap_rate': gap_rate, 'open_price': open_price, 'prev_close': prev_close})
                return True  # 탈락
            else:
                # 갭 초과 (+5% 초과) - 탈락 (과열)
                position.state = PositionState.DISQUALIFIED
                position.error_message = f'갭 과열 ({gap_rate:.2f}% > {gap_max}%)'
                self._log_event('INFO', 'GAP_DISQUALIFIED', 
                              f'{position.name}: 갭 과열로 탈락 (갭률: {gap_rate:.2f}% > {gap_max}%)',
                              code=position.code,
                              data={'gap_rate': gap_rate, 'open_price': open_price, 'prev_close': prev_close})
                return True  # 탈락
                
        except Exception as e:
            self._log_event('ERROR', 'GAP_CHECK_ERROR', 
                          f'{position.name}: 갭 확인 오류 - {e}',
                          code=position.code)
            position.state = PositionState.DISQUALIFIED
            position.error_message = f'갭 확인 오류: {e}'
            return True
    
    # =============================
    # 유니버스 구축
    # =============================
    
    def _get_universe_target_date(self) -> date:
        """유니버스 구축에 사용할 날짜 반환
        
        규칙:
        - 오후 4시~6시: 구축 불가 (None 반환)
        - 오후 6시~23:59: 당일 데이터 사용 (내일용)
        - 00:00~오후 4시: 전일 데이터 사용 (오늘용)
        """
        now = datetime.now()
        current_hour = now.hour
        today = now.date()
        
        # 오후 4시~6시: 구축 불가
        if 16 <= current_hour < 18:
            self._log_event('WARNING', 'UNIVERSE_BLOCKED', 
                          '유니버스 구축 불가 시간 (16:00-18:00)')
            return None
        
        if current_hour >= 18:
            # 저녁 6시 이후: 당일 데이터
            if is_trading_day(today):
                return today
            else:
                return get_prev_trading_day(today)
        else:
            # 오전 0시~오후 4시: 전일 데이터
            return get_prev_trading_day(today)
    
    def build_universe(self) -> List[UniverseStock]:
        """전일 상한가 종목 유니버스 구축
        
        1. 상한가 조건(29.5%+) 필터링
        2. KIS API로 시가총액 조회
        3. 시총 500억 이상 필터링
        4. 시총 높은 순으로 정렬 (진입 우선순위)
        """
        self._log_event('INFO', 'UNIVERSE_BUILD', '유니버스 구축 시작')
        
        candidates = []  # 1차 후보 (상한가 조건만)
        universe = []    # 최종 유니버스 (시총 필터 후)
        
        try:
            # 유니버스 대상 날짜 계산
            target_date = self._get_universe_target_date()
            
            # 4PM~6PM 사이면 구축 불가
            if target_date is None:
                self._log_event('WARNING', 'UNIVERSE_BLOCKED', 
                              '유니버스 구축 불가 시간대 (16:00-18:00)')
                return []
            
            target_date_str = target_date.strftime('%Y-%m-%d')
            
            self._log_event('INFO', 'UNIVERSE_DATE', f'유니버스 기준일: {target_date_str}')
            
            # 1차: 로컬 parquet 데이터에서 상한가 종목 조회
            bars_dir = Path("data/krx/bars") / f"date={target_date_str}"
            if bars_dir.exists():
                self._log_event('INFO', 'UNIVERSE_LOCAL', f'로컬 데이터 사용: {target_date_str}')
                try:
                    import pyarrow.parquet as pq
                    df = pq.read_table(bars_dir).to_pandas()
                    
                    for _, row in df.iterrows():
                        # 등락률 (change 컬럼: 소수점 비율, 예: 0.30 = 30%)
                        change_rate = row.get('change', 0) * 100  # 퍼센트로 변환
                        
                        # 상한가 조건: 등락률 ≥ 29.5%
                        if change_rate >= self.config.UPPER_LIMIT_RATE:
                            code = row.get('code', '')
                            name = row.get('name', '')
                            close = row.get('close', 0)
                            high = row.get('high', 0)
                            volume = row.get('volume', 0)
                            
                            # 거래대금 계산 (억원): 종가 * 거래량 / 1억
                            trading_value = (close * volume) / 100000000
                            
                            candidates.append({
                                'code': code,
                                'name': name,
                                'prev_close': close,
                                'prev_high': high,
                                'change_rate': change_rate,
                                'trading_value': trading_value
                            })
                    
                    self._log_event('INFO', 'UNIVERSE_CANDIDATES', 
                                  f'상한가 종목 {len(candidates)}개 발견, 필터링 시작')
                    
                except Exception as e:
                    self._log_event('WARNING', 'UNIVERSE_LOCAL_ERROR', f'로컬 데이터 로드 실패: {e}')
            
            # 2차: pykrx 폴백 (로컬 데이터 없을 경우)
            if not candidates:
                self._log_event('INFO', 'UNIVERSE_PYKRX', 'pykrx에서 데이터 조회')
                try:
                    from pykrx import stock
                    
                    prev_date = target_date.strftime('%Y%m%d')
                    
                    # 전 종목 티커 조회
                    kospi_tickers = stock.get_market_ticker_list(prev_date, market="KOSPI")
                    kosdaq_tickers = stock.get_market_ticker_list(prev_date, market="KOSDAQ")
                    all_tickers = kospi_tickers + kosdaq_tickers
                    
                    for code in all_tickers:
                        try:
                            ohlcv = stock.get_market_ohlcv_by_date(prev_date, prev_date, code)
                            if ohlcv.empty:
                                continue
                            
                            row = ohlcv.iloc[0]
                            change_rate = row.get('등락률', 0)
                            
                            if change_rate >= self.config.UPPER_LIMIT_RATE:
                                name = stock.get_market_ticker_name(code)
                                close = row.get('종가', 0)
                                high = row.get('고가', 0)
                                
                                candidates.append({
                                    'code': code,
                                    'name': name,
                                    'prev_close': close,
                                    'prev_high': high,
                                    'change_rate': change_rate,
                                    'trading_value': 0  # pykrx에서는 별도 계산 필요
                                })
                        except:
                            continue
                except ImportError:
                    self._log_event('WARNING', 'UNIVERSE_FALLBACK', 'pykrx 미설치')
            
            # 3단계: 시가총액 + 거래대금 필터링
            for cand in candidates:
                code = cand['code']
                name = cand['name']
                trading_value = cand.get('trading_value', 0)
                
                # 거래대금 필터: 300억 이상
                if trading_value < self.config.MIN_TRADING_VALUE:
                    self._log_event('INFO', 'UNIVERSE_SKIP_TV', 
                                  f'{name} 거래대금 미달 ({trading_value:.0f}억 < {self.config.MIN_TRADING_VALUE}억)',
                                  code=code)
                    continue
                
                # KIS API로 시총 조회
                market_cap = self._get_market_cap(code)
                time.sleep(0.1)  # API 호출 간격 (rate limit 방지)
                
                # 시총 필터: 1,000억 이상
                if market_cap < self.config.MIN_MARKET_CAP:
                    self._log_event('INFO', 'UNIVERSE_SKIP_MC', 
                                  f'{name} 시총 미달 ({market_cap:.0f}억 < {self.config.MIN_MARKET_CAP}억)',
                                  code=code)
                    continue
                
                # 모든 필터 통과
                universe.append(UniverseStock(
                    code=code,
                    name=name,
                    prev_close=cand['prev_close'],
                    prev_high=cand['prev_high'],
                    change_rate=cand['change_rate'],
                    market_cap=market_cap,
                    added_date=self.state.today
                ))
                
                self._log_event('INFO', 'UNIVERSE_ADD', 
                              f'{name} 유니버스 추가 (시총 {market_cap:.0f}억, 거래대금 {trading_value:.0f}억)',
                              code=code,
                              data={'change_rate': round(cand['change_rate'], 2), 'market_cap': market_cap, 'trading_value': trading_value})
            
            # 4단계: 시총 높은 순으로 정렬 (진입 우선순위)
            universe.sort(key=lambda x: x.market_cap, reverse=True)
            
            self._log_event('INFO', 'UNIVERSE_COMPLETE', 
                          f'유니버스 구축 완료: {len(universe)}개 종목 (시총순 정렬)')
            
            # DB에 유니버스 저장
            self._save_universe_to_db(universe, target_date_str)
            
        except Exception as e:
            self._log_event('ERROR', 'UNIVERSE_ERROR', f'유니버스 구축 실패: {e}')
        
        return universe
    
    def _save_universe_to_db(self, universe: List[UniverseStock], target_date: str):
        """유니버스를 DB에 저장 (히스토리 관리)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            for stock in universe:
                cursor.execute("""
                    INSERT OR REPLACE INTO auto_trading_universe 
                    (date, code, name, prev_close, change_rate, market_cap, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    target_date,
                    stock.code,
                    stock.name,
                    stock.prev_close,
                    stock.change_rate,
                    stock.market_cap,
                    datetime.now().isoformat()
                ))
            
            conn.commit()
            conn.close()
            self._log_event('INFO', 'UNIVERSE_DB_SAVED', f'유니버스 DB 저장 완료: {len(universe)}개')
        except Exception as e:
            self._log_event('ERROR', 'UNIVERSE_DB_ERROR', f'유니버스 DB 저장 실패: {e}')
    
    def _build_universe_from_db(self) -> List[UniverseStock]:
        """DB에서 유니버스 구축 (폴백)"""
        universe = []
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 어제 날짜
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            
            # 로컬 bars 데이터에서 조회
            bars_dir = Path("data/krx/bars")
            if bars_dir.exists():
                for partition in bars_dir.iterdir():
                    if partition.is_dir() and partition.name.startswith('date='):
                        part_date = partition.name.split('=')[1]
                        if part_date == yesterday:
                            # parquet 파일 로드
                            try:
                                import pyarrow.parquet as pq
                                df = pq.read_table(partition).to_pandas()
                                
                                for _, row in df.iterrows():
                                    change_rate = row.get('change_rate', 0)
                                    market_cap = row.get('market_cap', 0) / 100000000
                                    
                                    if change_rate >= self.config.UPPER_LIMIT_RATE:
                                        if market_cap >= self.config.MIN_MARKET_CAP:
                                            universe.append(UniverseStock(
                                                code=row.get('code', ''),
                                                name=row.get('name', ''),
                                                prev_close=row.get('close', 0),
                                                prev_high=row.get('high', 0),
                                                change_rate=change_rate,
                                                market_cap=market_cap,
                                                added_date=self.state.today
                                            ))
                            except Exception as e:
                                logger.error(f"Parquet 로드 실패: {e}")
            
            conn.close()
        except Exception as e:
            logger.error(f"DB 유니버스 구축 실패: {e}")
        
        return universe
    
    # =============================
    # 시그널 엔진
    # =============================
    
    def check_entry_signal(self, position: Position) -> bool:
        """진입 시그널 확인: 갭 +2%~+5% 후 전일종가(0%) 도달 시 매수"""
        try:
            price_data = self._get_current_price(position.code)
            if not price_data:
                return False
            
            current_price = price_data.get('current_price', 0)
            open_price = price_data.get('open_price', 0)
            prev_close = position.prev_close
            
            if prev_close <= 0 or current_price <= 0:
                return False
            
            # 현재가 업데이트
            position.current_price = current_price
            
            # KOSPI 시장 필터 체크
            if self.config.USE_MARKET_FILTER:
                if not self._check_market_filter():
                    self._log_event('INFO', 'MARKET_FILTER_BLOCKED', 
                                  f'KOSPI 5일선 하회로 진입 보류',
                                  code=position.code)
                    return False
            
            # 진입 조건: 현재가가 전일종가 이하로 내려왔을 때 매수
            # (갭상승 후 눌림목에서 전일종가 지지 확인)
            if self.config.ENTRY_AT_PREV_CLOSE:
                # 전일종가 근처 또는 이하 도달 체크 (오차범위 0.3%)
                tolerance = prev_close * 0.003  # 0.3% 허용
                
                if current_price <= prev_close + tolerance:
                    position.gap_confirms += 1
                    self._log_event('INFO', 'ENTRY_SIGNAL', 
                                  f'전일종가 도달 확인 {position.gap_confirms}/{self.config.GAP_CONFIRM_COUNT}',
                                  code=position.code,
                                  data={'current_price': current_price, 'prev_close': prev_close, 
                                        'tolerance': tolerance})
                    
                    if position.gap_confirms >= self.config.GAP_CONFIRM_COUNT:
                        self._log_event('INFO', 'ENTRY_CONFIRMED', 
                                      f'진입 시그널 확정 - 전일종가({prev_close}) 도달',
                                      code=position.code)
                        return True
                else:
                    # 아직 전일종가까지 내려오지 않음
                    if position.gap_confirms > 0:
                        self._log_event('INFO', 'ENTRY_RESET', 
                                      f'전일종가 미도달, 카운트 유지',
                                      code=position.code,
                                      data={'current_price': current_price, 'prev_close': prev_close})
            
            return False
        except Exception as e:
            self._log_event('ERROR', 'SIGNAL_ERROR', f'시그널 확인 실패: {e}',
                          code=position.code)
            return False
    
    def check_exit_signal(self, position: Position) -> Tuple[bool, str]:
        """청산 시그널 확인 (TP/전일종가SL/EOD)
        Returns: (should_exit, reason)
        """
        try:
            price_data = self._get_current_price(position.code)
            if not price_data:
                return False, ""
            
            current_price = price_data.get('current_price', 0)
            position.current_price = current_price
            
            if position.entry_price <= 0 or current_price <= 0:
                return False, ""
            
            # 손익률 계산
            pnl_rate = (current_price - position.entry_price) / position.entry_price * 100
            position.unrealized_pnl = (current_price - position.entry_price) * position.quantity
            position.unrealized_pnl_rate = pnl_rate
            
            # TP 체크 (+10%)
            if pnl_rate >= self.config.TAKE_PROFIT_RATE:
                return True, "TP"
            
            # SL 체크 (-4%)
            if pnl_rate <= self.config.STOP_LOSS_RATE:
                self._log_event('INFO', 'SL_FIXED', 
                              f'손절 - 손익률({pnl_rate:.2f}%) ≤ {self.config.STOP_LOSS_RATE}%',
                              code=position.code)
                return True, "SL"
            
            # EOD 체크
            now = datetime.now()
            eod_start = datetime.strptime(f"{now.strftime('%Y-%m-%d')} {self.config.EOD_SELL_START}", 
                                         '%Y-%m-%d %H:%M')
            if now >= eod_start:
                return True, "EOD"
            
            return False, ""
        except Exception as e:
            self._log_event('ERROR', 'EXIT_CHECK_ERROR', f'청산 시그널 확인 실패: {e}',
                          code=position.code)
            return False, ""
    
    # =============================
    # 실행 엔진
    # =============================
    
    def execute_entry(self, position: Position) -> bool:
        """진입 주문 실행 (전일종가 지정가 또는 시가 지정가 주문)"""
        try:
            # 투자 금액 계산 (1/N 방식: 총자산 / 최대 포지션 수)
            position_amount = self.state.total_asset / self.config.MAX_POSITIONS
            
            # 현재가 조회
            price_data = self._get_current_price(position.code)
            if not price_data:
                self._log_event('ERROR', 'ENTRY_FAIL', '현재가 조회 실패', code=position.code)
                position.state = PositionState.SKIPPED
                position.error_message = '현재가 조회 실패'
                return False
            
            current_price = price_data.get('current_price', 0)
            open_price = price_data.get('open_price', 0)
            
            if current_price <= 0:
                position.state = PositionState.SKIPPED
                position.error_message = '유효하지 않은 가격'
                return False
            
            # 주문가 결정: 전일종가 지정가 > 시가 지정가 > 현재가 지정가
            if self.config.USE_LIMIT_ORDER_AT_PREV_CLOSE and position.prev_close > 0:
                # AI 예측 모드: 전일종가 지정가 주문
                order_price = position.prev_close
                self._log_event('INFO', 'ENTRY_PRICE', 
                              f'전일종가 지정가 주문: {order_price}원',
                              code=position.code)
            elif self.config.USE_LIMIT_ORDER_AT_OPEN and open_price > 0:
                # 시가 지정가 주문
                order_price = open_price
                self._log_event('INFO', 'ENTRY_PRICE', 
                              f'시가 지정가 주문: {order_price}원',
                              code=position.code)
            else:
                # 폴백: 현재가 기준 지정가
                ask_price = price_data.get('ask_price', current_price)
                order_price = ask_price + (self.config.ORDER_SLIPPAGE_TICKS * self._get_tick_size(current_price))
            
            # 수량 계산
            quantity = int(position_amount / order_price)
            
            if quantity <= 0:
                self._log_event('WARNING', 'ENTRY_SKIP', '매수 수량 0', 
                              code=position.code,
                              data={'amount': position_amount, 'price': order_price})
                position.state = PositionState.SKIPPED
                position.error_message = '매수 수량 부족'
                return False
            
            # 최대 포지션 수 체크
            active_positions = sum(1 for p in self.state.positions.values() 
                                  if p.state == PositionState.ENTERED)
            if active_positions >= self.config.MAX_POSITIONS:
                self._log_event('WARNING', 'ENTRY_SKIP', '최대 포지션 수 도달',
                              code=position.code)
                position.state = PositionState.SKIPPED
                position.error_message = '최대 포지션 수 도달'
                return False
            
            # 주문 실행 (지정가 주문)
            position.state = PositionState.ENTRY_PENDING
            position.limit_order_price = order_price  # 지정가 기록
            
            result = self._place_order(position.code, quantity, 'buy', order_price)
            
            if 'error' in result:
                self._log_event('ERROR', 'ENTRY_FAIL', f'매수 주문 실패: {result["error"]}',
                              code=position.code)
                position.error_message = result['error']
                position.retry_count += 1
                
                if position.retry_count >= self.config.ORDER_RETRY_COUNT:
                    position.state = PositionState.SKIPPED
                return False
            
            position.order_id = result.get('order_no', '')
            position.pending_quantity = quantity
            position.order_time = datetime.now().isoformat()  # 주문 시간 기록 (9:30 취소 체크용)
            
            self._log_event('INFO', 'ENTRY_ORDER', f'시가 지정가 매수 주문 접수',
                          code=position.code,
                          data={'order_no': position.order_id, 'qty': quantity, 'price': order_price, 'type': 'limit_at_open'})
            
            return True
        except Exception as e:
            self._log_event('ERROR', 'ENTRY_ERROR', f'진입 실행 오류: {e}',
                          code=position.code)
            position.state = PositionState.ERROR
            position.error_message = str(e)
            return False
    
    def execute_exit(self, position: Position, reason: str) -> bool:
        """청산 주문 실행"""
        try:
            if position.quantity <= 0:
                self._log_event('WARNING', 'EXIT_SKIP', '청산할 수량 없음',
                              code=position.code)
                return False
            
            position.state = PositionState.EXIT_PENDING
            position.exit_reason = reason
            
            # 시장가 매도 (빠른 청산을 위해)
            result = self._place_order(position.code, position.quantity, 'sell', 0)
            
            if 'error' in result:
                self._log_event('ERROR', 'EXIT_FAIL', f'매도 주문 실패: {result["error"]}',
                              code=position.code)
                position.error_message = result['error']
                position.retry_count += 1
                return False
            
            position.order_id = result.get('order_no', '')
            
            self._log_event('INFO', 'EXIT_ORDER', f'매도 주문 접수 ({reason})',
                          code=position.code,
                          data={'order_no': position.order_id, 'qty': position.quantity, 'reason': reason})
            
            return True
        except Exception as e:
            self._log_event('ERROR', 'EXIT_ERROR', f'청산 실행 오류: {e}',
                          code=position.code)
            return False
    
    def confirm_order(self, position: Position) -> bool:
        """주문 체결 확인"""
        try:
            if not position.order_id:
                return False
            
            status = self._get_order_status(position.order_id)
            
            if 'error' in status:
                return False
            
            exec_qty = status.get('exec_qty', 0)
            exec_price = status.get('exec_price', 0)
            remain_qty = status.get('remain_qty', 0)
            
            if position.state == PositionState.ENTRY_PENDING:
                if exec_qty > 0:
                    position.quantity = exec_qty
                    position.entry_price = exec_price
                    position.entry_time = datetime.now().isoformat()
                    position.pending_quantity = remain_qty
                    
                    if remain_qty == 0:
                        position.state = PositionState.ENTERED
                        self._log_event('INFO', 'ENTRY_FILLED', f'매수 체결 완료',
                                      code=position.code,
                                      data={'qty': exec_qty, 'price': exec_price})
                        
                        # ntfy 알림: 매수 완료
                        send_ntfy_notification(
                            title="✅ 매수 체결 완료",
                            message=f"[{position.name}] {exec_qty}주 @ {exec_price:,}원",
                            priority="high",
                            tags=["white_check_mark", "moneybag"]
                        )
                        return True
                    else:
                        self._log_event('INFO', 'ENTRY_PARTIAL', f'부분 체결',
                                      code=position.code,
                                      data={'exec_qty': exec_qty, 'remain_qty': remain_qty})
            
            elif position.state == PositionState.EXIT_PENDING:
                if remain_qty == 0:
                    # 청산 완료
                    pnl = (exec_price - position.entry_price) * exec_qty
                    pnl_rate = (exec_price - position.entry_price) / position.entry_price * 100 if position.entry_price > 0 else 0
                    
                    position.state = PositionState.CLOSED
                    position.exit_time = datetime.now().isoformat()
                    position.unrealized_pnl = pnl
                    position.unrealized_pnl_rate = pnl_rate
                    
                    # 통계 업데이트
                    self.state.total_trades += 1
                    if pnl >= 0:
                        self.state.winning_trades += 1
                    else:
                        self.state.losing_trades += 1
                    
                    self.state.daily_pnl += pnl
                    
                    # DB 기록
                    self._record_trade(position, 'sell', exec_qty, exec_price, pnl, pnl_rate)
                    
                    self._log_event('INFO', 'EXIT_FILLED', f'매도 체결 완료 ({position.exit_reason})',
                                  code=position.code,
                                  data={'qty': exec_qty, 'price': exec_price, 
                                        'pnl': pnl, 'pnl_rate': pnl_rate})
                    
                    # ntfy 알림: 청산 완료 (TP/SL)
                    emoji = "🎉" if pnl >= 0 else "😢"
                    reason_text = {
                        'TP': '익절',
                        'SL': '손절', 
                        'EOD': '장마감 청산',
                        'MANUAL': '수동 청산'
                    }.get(position.exit_reason, position.exit_reason)
                    send_ntfy_notification(
                        title=f"{emoji} 청산 완료 ({reason_text})",
                        message=f"[{position.name}] {exec_qty}주 @ {exec_price:,}원\n손익: {pnl:+,.0f}원 ({pnl_rate:+.2f}%)",
                        priority="high" if abs(pnl_rate) >= 5 else "default",
                        tags=["chart_with_upwards_trend" if pnl >= 0 else "chart_with_downwards_trend", "money_with_wings"]
                    )
                    return True
            
            return False
        except Exception as e:
            self._log_event('ERROR', 'CONFIRM_ERROR', f'체결 확인 오류: {e}',
                          code=position.code)
            return False
    
    def _record_trade(self, position: Position, trade_type: str, 
                      quantity: int, price: float, pnl: float, pnl_rate: float):
        """거래 내역 DB 기록"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO auto_trading_trades 
                (trade_date, code, name, trade_type, quantity, price, amount, exit_reason, pnl, pnl_rate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.state.today,
                position.code,
                position.name,
                trade_type,
                quantity,
                price,
                quantity * price,
                position.exit_reason if trade_type == 'sell' else None,
                pnl if trade_type == 'sell' else None,
                pnl_rate if trade_type == 'sell' else None
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"거래 기록 실패: {e}")
    
    def _get_tick_size(self, price: int) -> int:
        """호가 단위 계산"""
        if price < 1000:
            return 1
        elif price < 5000:
            return 5
        elif price < 10000:
            return 10
        elif price < 50000:
            return 50
        elif price < 100000:
            return 100
        elif price < 500000:
            return 500
        else:
            return 1000
    
    # =============================
    # 메인 루프
    # =============================
    
    def _determine_phase(self) -> StrategyPhase:
        """현재 시간에 따른 전략 단계 결정"""
        now = datetime.now()
        current_time = now.strftime('%H:%M')
        
        # 주말 체크
        if now.weekday() >= 5:
            return StrategyPhase.IDLE
        
        # 휴장일 체크
        if not is_trading_day(now.date()):
            return StrategyPhase.IDLE
        
        if current_time < "08:40":
            return StrategyPhase.IDLE
        elif current_time < "09:00":
            return StrategyPhase.PREPARING
        elif current_time < "09:03":
            return StrategyPhase.ENTRY_WINDOW
        elif current_time < "15:20":
            return StrategyPhase.MONITORING
        elif current_time < "15:28":
            return StrategyPhase.EOD_CLOSING
        else:
            return StrategyPhase.CLOSED
    
    def _run_loop(self):
        """메인 실행 루프"""
        self._log_event('INFO', 'ENGINE_START', '자동매매 엔진 시작')
        
        while self._running:
            try:
                # 단계 결정
                new_phase = self._determine_phase()
                
                if new_phase != self.state.phase:
                    self._log_event('INFO', 'PHASE_CHANGE', 
                                  f'{self.state.phase.value} → {new_phase.value}')
                    self.state.phase = new_phase
                
                # 단계별 처리
                if self.state.phase == StrategyPhase.PREPARING:
                    self._phase_preparing()
                elif self.state.phase == StrategyPhase.ENTRY_WINDOW:
                    self._phase_entry_window()
                elif self.state.phase == StrategyPhase.MONITORING:
                    self._phase_monitoring()
                elif self.state.phase == StrategyPhase.EOD_CLOSING:
                    self._phase_eod_closing()
                elif self.state.phase == StrategyPhase.CLOSED:
                    self._phase_closed()
                
                # 상태 업데이트
                self.state.last_update = datetime.now().isoformat()
                self._save_state()
                
                # 루프 간격 (1초)
                time.sleep(1)
                
            except Exception as e:
                self._log_event('ERROR', 'LOOP_ERROR', f'루프 오류: {e}')
                time.sleep(5)
        
        self._log_event('INFO', 'ENGINE_STOP', '자동매매 엔진 중지')
    
    def _phase_preparing(self):
        """준비 단계 (08:40~09:00)"""
        # 토큰 확인
        if not self._get_access_token():
            self._log_event('ERROR', 'PREPARE_FAIL', '토큰 발급 실패')
            return
        
        # 계좌 잔고 확인
        balance = self._get_account_balance()
        if 'error' not in balance:
            self.state.total_asset = balance.get('total_eval', 0) + balance.get('deposit', 0)
            self.state.available_cash = balance.get('available', 0)
        
        # 유니버스 구축 (아직 안했으면)
        if not self.state.universe:
            self.state.universe = self.build_universe()
            
            # 포지션 초기화
            for stock in self.state.universe:
                if stock.code not in self.state.positions:
                    self.state.positions[stock.code] = Position(
                        code=stock.code,
                        name=stock.name,
                        state=PositionState.WATCHING,
                        prev_close=stock.prev_close
                    )
            
            # ntfy 알림: PREPARING 단계 유니버스 구축
            if self.state.universe:
                stock_names = [s.name for s in self.state.universe[:10]]  # 최대 10개
                stock_list = ", ".join(stock_names)
                if len(self.state.universe) > 10:
                    stock_list += f" 외 {len(self.state.universe) - 10}개"
                send_ntfy_notification(
                    title="🎯 유니버스 구축 완료",
                    message=f"[{self.state.today}] 감시 종목 {len(self.state.universe)}개\n{stock_list}",
                    priority="default",
                    tags=["chart_with_upwards_trend", "stock"]
                )
        
        time.sleep(5)  # 준비 단계는 느리게
    
    def _phase_entry_window(self):
        """진입 구간 (09:00~09:30)"""
        now = datetime.now()
        cancel_time = datetime.strptime(f"{now.strftime('%Y-%m-%d')} {self.config.ENTRY_CANCEL_TIME}", 
                                        '%Y-%m-%d %H:%M')
        
        for code, position in self.state.positions.items():
            if position.state == PositionState.WATCHING:
                # 먼저 갭 조건 확인하여 탈락 여부 판정
                disqualified = self._check_gap_disqualification(position)
                if disqualified:
                    continue  # 탈락 종목은 건너뜀
                
                # 갭 시그널 확인 (갭 조건 충족 종목만)
                if self.check_entry_signal(position):
                    self.execute_entry(position)
            
            elif position.state == PositionState.ENTRY_PENDING:
                # 9:30 미체결 취소 체크 (AI 예측 모드)
                if now >= cancel_time and position.order_time:
                    # 취소 시간 도달 - 미체결 주문 취소
                    cancel_success = self._cancel_order(
                        position.order_id, 
                        position.code, 
                        position.pending_quantity
                    )
                    if cancel_success:
                        position.state = PositionState.SKIPPED
                        position.error_message = f'{self.config.ENTRY_CANCEL_TIME} 미체결 취소'
                        self._log_event('INFO', 'ENTRY_CANCEL_TIME', 
                                      f'{position.name}({position.code}): {self.config.ENTRY_CANCEL_TIME} 미체결로 주문 취소')
                    else:
                        # 취소 실패 - 체결 확인 계속
                        self.confirm_order(position)
                    continue
                
                # 미체결 타임아웃 체크
                if self._check_pending_timeout(position):
                    # 타임아웃 시 주문 취소
                    cancel_success = self._cancel_order(
                        position.entry_order_no, 
                        position.code, 
                        position.quantity
                    )
                    if cancel_success:
                        position.state = PositionState.SKIPPED
                        position.error_message = f'진입 미체결 타임아웃 ({self.config.ENTRY_PENDING_TIMEOUT}초)'
                        self._log_event('WARNING', 'ENTRY_TIMEOUT', 
                                      f'{position.code}: 미체결 타임아웃으로 주문 취소')
                    else:
                        # 취소 실패 시 체결 확인 계속
                        self.confirm_order(position)
                else:
                    # 체결 확인
                    self.confirm_order(position)
        
        time.sleep(0.5)  # 빠르게 체크
    
    def _phase_monitoring(self):
        """장중 모니터링 (09:03~15:20)"""
        # 진입 윈도우 종료 후 미체결 진입 주문 처리
        if self.config.ENTRY_ORDER_CANCEL_AFTER_WINDOW:
            for code, position in list(self.state.positions.items()):
                if position.state == PositionState.ENTRY_PENDING:
                    # 진입 윈도우가 끝났으므로 미체결 주문 취소
                    cancel_success = self._cancel_order(
                        position.entry_order_no, 
                        position.code, 
                        position.quantity
                    )
                    if cancel_success:
                        position.state = PositionState.SKIPPED
                        position.error_message = '진입 윈도우 종료, 미체결 취소'
                        self._log_event('INFO', 'ENTRY_WINDOW_EXPIRED', 
                                      f'{position.code}: 진입 윈도우 종료로 미체결 취소')
                    else:
                        # 취소 실패 - 부분 체결 가능성, 체결 확인 계속
                        self.confirm_order(position)
                        self._log_event('WARNING', 'CANCEL_FAILED', 
                                      f'{position.code}: 미체결 취소 실패, 체결 확인 계속')
        
        for code, position in self.state.positions.items():
            # 미체결 주문 확인 (취소 실패한 경우)
            if position.state == PositionState.ENTRY_PENDING:
                self.confirm_order(position)
            
            # 청산 시그널 확인
            elif position.state == PositionState.ENTERED:
                should_exit, reason = self.check_exit_signal(position)
                if should_exit:
                    self.execute_exit(position, reason)
            
            # 청산 주문 체결 확인
            elif position.state == PositionState.EXIT_PENDING:
                self.confirm_order(position)
        
        # 일일 최대 손실 체크
        if self.state.total_asset > 0:
            daily_loss_rate = self.state.daily_pnl / self.state.total_asset * 100
            if daily_loss_rate <= self.config.MAX_DAILY_LOSS_RATE:
                self._log_event('WARNING', 'DAILY_LOSS_LIMIT', 
                              f'일일 손실 한도 도달: {daily_loss_rate:.2f}%')
                # 모든 WATCHING 상태를 SKIPPED로 변경
                for position in self.state.positions.values():
                    if position.state == PositionState.WATCHING:
                        position.state = PositionState.SKIPPED
                        position.error_message = '일일 손실 한도 도달'
        
        time.sleep(2)  # 2초 간격
    
    def _phase_eod_closing(self):
        """EOD 청산 (15:20~15:28)"""
        for code, position in self.state.positions.items():
            if position.state == PositionState.ENTERED:
                self.execute_exit(position, "EOD")
            elif position.state == PositionState.EXIT_PENDING:
                self.confirm_order(position)
        
        time.sleep(1)
    
    def _phase_closed(self):
        """장 종료 후"""
        # 잔여 포지션 강제 처리
        for position in self.state.positions.values():
            if position.state == PositionState.ENTERED:
                self._log_event('WARNING', 'LEFTOVER_POSITION', 
                              f'장종료 후 미청산 포지션',
                              code=position.code)
        
        time.sleep(60)  # 1분 대기
    
    # =============================
    # 공개 API
    # =============================
    
    def start(self):
        """자동매매 시작"""
        if self._running:
            return {'success': False, 'error': '이미 실행 중'}
        
        self._running = True
        self.state.is_running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        
        self._log_event('INFO', 'STRATEGY_START', '자동매매 전략 시작')
        self._save_state()
        
        return {'success': True, 'message': '자동매매 시작됨'}
    
    def stop(self):
        """자동매매 중지"""
        self._running = False
        self.state.is_running = False
        
        if self._thread:
            self._thread.join(timeout=5)
        
        self._log_event('INFO', 'STRATEGY_STOP', '자동매매 전략 중지')
        self._save_state()
        
        return {'success': True, 'message': '자동매매 중지됨'}
    
    def get_status(self) -> dict:
        """현재 상태 조회"""
        # 자산 정보 갱신 (캐시: 1분 이내면 스킵)
        import time
        now = time.time()
        if not hasattr(self, '_last_balance_check') or now - self._last_balance_check > 60:
            try:
                balance = self._get_account_balance()
                if 'error' not in balance:
                    self.state.total_asset = balance.get('total_eval', 0)  # 총평가금액 (예수금 포함)
                    self.state.available_cash = balance.get('available', 0)
                    self._last_balance_check = now
            except:
                pass
        return self.state.to_dict()
    
    def manual_buy(self, code: str, quantity: int, auto_quantity: bool = False) -> dict:
        """수동 매수 (auto_quantity=True이면 1/N 비율로 자동 계산)"""
        try:
            # 현재가 조회
            price_data = self._get_current_price(code)
            if not price_data:
                return {'error': '현재가 조회 실패'}
            
            current_price = price_data.get('current_price', 0)
            ask_price = price_data.get('ask_price', current_price)
            
            if current_price <= 0:
                return {'error': '유효하지 않은 가격'}
            
            # 수량 계산 (auto_quantity=True이면 1/N 비율)
            if auto_quantity or quantity <= 0:
                # 계좌 정보 갱신
                self._update_balance()
                position_amount = self.state.total_asset / self.config.MAX_POSITIONS
                order_price = ask_price + (self.config.ORDER_SLIPPAGE_TICKS * self._get_tick_size(current_price))
                quantity = int(position_amount / order_price)
                
                if quantity <= 0:
                    return {'error': f'매수 수량 부족 (투자금액: {position_amount:,.0f}원, 주문가: {order_price:,.0f}원)'}
                
                self._log_event('INFO', 'MANUAL_BUY_CALC', f'수동 매수 수량 자동 계산: 1/{self.config.MAX_POSITIONS}',
                              code=code,
                              data={'position_amount': position_amount, 'order_price': order_price, 'quantity': quantity})
            
            result = self._place_order(code, quantity, 'buy', 0)
            
            if 'error' in result:
                return result
            
            # 포지션 생성/업데이트
            if code not in self.state.positions:
                self.state.positions[code] = Position(
                    code=code,
                    name='',  # 이름은 나중에 업데이트
                    state=PositionState.ENTRY_PENDING,
                    prev_close=price_data.get('prev_close', 0)
                )
            
            position = self.state.positions[code]
            position.state = PositionState.ENTRY_PENDING
            position.order_id = result.get('order_no', '')
            position.pending_quantity = quantity
            
            self._log_event('INFO', 'MANUAL_BUY', f'수동 매수 주문 (auto={auto_quantity})',
                          code=code,
                          data={'qty': quantity, 'order_no': result.get('order_no', ''), 'auto_quantity': auto_quantity})
            
            self._save_state()
            return {**result, 'quantity': quantity}
        except Exception as e:
            return {'error': str(e)}
    
    def manual_sell(self, code: str, quantity: int = 0) -> dict:
        """수동 매도 (quantity=0이면 전량)"""
        try:
            if code not in self.state.positions:
                return {'error': '해당 종목 포지션 없음'}
            
            position = self.state.positions[code]
            
            sell_qty = quantity if quantity > 0 else position.quantity
            if sell_qty <= 0:
                return {'error': '매도할 수량 없음'}
            
            result = self._place_order(code, sell_qty, 'sell', 0)
            
            if 'error' in result:
                return result
            
            position.state = PositionState.EXIT_PENDING
            position.exit_reason = 'MANUAL'
            position.order_id = result.get('order_no', '')
            
            self._log_event('INFO', 'MANUAL_SELL', f'수동 매도 주문',
                          code=code,
                          data={'qty': sell_qty, 'order_no': result.get('order_no', '')})
            
            self._save_state()
            return result
        except Exception as e:
            return {'error': str(e)}
    
    def refresh_positions(self):
        """포지션 동기화 (계좌 잔고 기준)"""
        try:
            balance = self._get_account_balance()
            if 'error' in balance:
                return balance
            
            holdings = balance.get('holdings', {})
            
            # 계좌 정보 업데이트
            self.state.total_asset = balance.get('total_eval', 0)  # 총평가금액 (예수금 포함)
            self.state.available_cash = balance.get('available', 0)
            
            # 포지션 동기화
            for code, holding in holdings.items():
                if code in self.state.positions:
                    position = self.state.positions[code]
                    position.quantity = holding['quantity']
                    position.current_price = holding['current_price']
                    position.entry_price = holding['avg_price']
                    position.unrealized_pnl = holding['profit_loss']
                    position.unrealized_pnl_rate = holding['profit_rate']
                    
                    if position.quantity > 0 and position.state not in [PositionState.ENTERED, PositionState.EXIT_PENDING]:
                        position.state = PositionState.ENTERED
                else:
                    # 새로운 포지션 (외부에서 매수한 경우)
                    self.state.positions[code] = Position(
                        code=code,
                        name=holding['name'],
                        state=PositionState.ENTERED,
                        quantity=holding['quantity'],
                        entry_price=holding['avg_price'],
                        current_price=holding['current_price'],
                        unrealized_pnl=holding['profit_loss'],
                        unrealized_pnl_rate=holding['profit_rate']
                    )
            
            self._log_event('INFO', 'POSITIONS_SYNCED', f'포지션 동기화 완료')
            self._save_state()
            
            return {'success': True, 'holdings': holdings}
        except Exception as e:
            return {'error': str(e)}
    
    def get_trade_history(self, days: int = 7) -> list:
        """거래 내역 조회"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            
            cursor.execute("""
                SELECT * FROM auto_trading_trades
                WHERE trade_date >= ?
                ORDER BY created_at DESC
            """, (start_date,))
            
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logger.error(f"거래 내역 조회 실패: {e}")
            return []


# =============================
# 전역 인스턴스 (Flask 앱에서 사용)
# =============================
try:
    import pandas as pd
except ImportError:
    pd = None

# 모의/실전 투자 엔진 각각 유지
_auto_trading_engine_mock: Optional[AutoTradingEngine] = None
_auto_trading_engine_real: Optional[AutoTradingEngine] = None
_current_mode: str = "mock"  # 현재 활성 모드

def get_auto_trading_engine(mode: str = None) -> AutoTradingEngine:
    """자동매매 엔진 싱글톤 (모의/실전 분리)"""
    global _auto_trading_engine_mock, _auto_trading_engine_real, _current_mode
    
    # 모드 지정이 없으면 현재 모드 사용
    if mode is None:
        mode = _current_mode
    
    db_path = os.environ.get('DB_PATH', os.path.dirname(__file__))
    if db_path and db_path != os.path.dirname(__file__):
        db_file = os.path.join(db_path, 'mystock.db')
    else:
        db_file = os.path.join(os.path.dirname(__file__), 'mystock.db')
    
    is_mock = (mode == "mock")
    
    if is_mock:
        if _auto_trading_engine_mock is None:
            _auto_trading_engine_mock = AutoTradingEngine(db_file, is_mock=True)
        return _auto_trading_engine_mock
    else:
        if _auto_trading_engine_real is None:
            _auto_trading_engine_real = AutoTradingEngine(db_file, is_mock=False)
        return _auto_trading_engine_real


def set_auto_trading_mode(mode: str) -> dict:
    """자동매매 모드 전환 (mock/real)"""
    global _current_mode, _auto_trading_engine_mock, _auto_trading_engine_real
    
    if mode not in ("mock", "real"):
        return {"success": False, "error": "Invalid mode. Use 'mock' or 'real'"}
    
    # 현재 활성 엔진이 실행 중이면 중지
    current_engine = get_auto_trading_engine(_current_mode)
    if current_engine._running:
        current_engine.stop()
    
    _current_mode = mode
    
    # 새 모드의 엔진 초기화
    new_engine = get_auto_trading_engine(mode)
    
    return {
        "success": True,
        "mode": mode,
        "label": "모의투자" if mode == "mock" else "실전투자",
        "is_mock": mode == "mock"
    }


def get_auto_trading_mode() -> dict:
    """현재 자동매매 모드 조회"""
    global _current_mode
    return {
        "mode": _current_mode,
        "label": "모의투자" if _current_mode == "mock" else "실전투자",
        "is_mock": _current_mode == "mock"
    }


def build_universe_for_date(target_date: str) -> dict:
    """
    특정 날짜의 데이터로 유니버스 구축 (스케줄러에서 호출)
    
    Args:
        target_date: 유니버스 기준 날짜 (YYYY-MM-DD 형식)
        
    Returns:
        {"success": True/False, "count": N, "error": "..."}
    """
    from pathlib import Path
    import pyarrow.parquet as pq
    
    try:
        # 현재 엔진 가져오기
        engine = get_auto_trading_engine()
        
        # 대상 날짜 데이터 존재 확인
        bars_dir = Path("data/krx/bars") / f"date={target_date}"
        if not bars_dir.exists():
            return {"success": False, "error": f"Data not found for {target_date}"}
        
        # 데이터 로드
        df = pq.read_table(bars_dir).to_pandas()
        
        if df.empty:
            return {"success": False, "error": f"Empty data for {target_date}"}
        
        # 상한가 종목 필터링
        candidates = []
        for _, row in df.iterrows():
            change_rate = row.get('change', 0) * 100
            
            if change_rate >= engine.config.UPPER_LIMIT_RATE:
                candidates.append({
                    'code': row.get('code', ''),
                    'name': row.get('name', ''),
                    'prev_close': row.get('close', 0),
                    'prev_high': row.get('high', 0),
                    'change_rate': change_rate
                })
        
        # 유니버스 구축 (MIN_MARKET_CAP=0이면 시총 조건 없음)
        universe = []
        for cand in candidates:
            market_cap = engine._get_market_cap(cand['code'])
            time.sleep(0.1)
            
            # MIN_MARKET_CAP=0이면 모든 종목 통과
            if market_cap >= engine.config.MIN_MARKET_CAP:
                universe.append(UniverseStock(
                    code=cand['code'],
                    name=cand['name'],
                    prev_close=cand['prev_close'],
                    prev_high=cand['prev_high'],
                    change_rate=cand['change_rate'],
                    market_cap=market_cap,
                    added_date=target_date
                ))
        
        # 시총 높은 순 정렬
        universe.sort(key=lambda x: x.market_cap, reverse=True)
        
        # 기존 유니버스 및 positions 클리어 (데이터 섞임 방지)
        engine.state.universe = []
        # ENTERED, EXIT_PENDING 상태가 아닌 포지션만 제거
        from auto_trading_strategy1 import PositionState
        positions_to_keep = {k: v for k, v in engine.state.positions.items() 
                            if v.state in (PositionState.ENTERED, PositionState.EXIT_PENDING)}
        engine.state.positions = positions_to_keep
        
        # 새 유니버스 저장
        engine.state.universe = universe
        
        # 새 유니버스 종목을 positions에 추가
        for stock in universe:
            if stock.code not in engine.state.positions:
                engine.state.positions[stock.code] = Position(
                    code=stock.code,
                    name=stock.name,
                    state=PositionState.WATCHING,
                    prev_close=stock.prev_close,
                    prev_high=stock.prev_high,
                    market_cap=stock.market_cap
                )
        
        # DB에 저장
        engine._save_universe_to_db(universe, target_date)
        
        engine._log_event('INFO', 'UNIVERSE_BUILD_API', 
                         f'유니버스 구축 완료: {len(universe)}종목 (기준일: {target_date})')
        
        return {
            "success": True, 
            "count": len(universe), 
            "target_date": target_date,
            "stocks": [{"code": s.code, "name": s.name, "market_cap": s.market_cap} for s in universe[:10]]
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

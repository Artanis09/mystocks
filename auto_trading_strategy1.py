"""
자동매매 핵심 엔진 (개편 버전)

특징:
- 특정 전략(상한가 등)에 의존하지 않고 사용자가 서버에 등록한 종목(target_stock)을 대상으로 매매
- 사용자가 설정한 매수 스케줄(BUY_SCHEDULE)에 따라 지정된 시간에 자동 매수
- 익절(TP), 손절(SL), 장마감 청산(EOD) 규칙에 따른 자동 매도
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
# 전략 상수
# =============================
def is_trading_day(check_date: date = None) -> bool:
    """휴장일 체크 없이 항상 True 반환 (사용자 요청)"""
    return True

class StrategyConfig:
    """전략 파라미터 설정 (매매전략 설정 기반)"""
    # 진입 조건 (유니버스 구축용)
    UPPER_LIMIT_RATE = 29.5      # 상한가 기준 수익률 (%)
    MIN_MARKET_CAP = 500         # 최소 시가총액 (억원)
    GAP_THRESHOLD = 2.0          # 시가 갭 기준 (%)
    GAP_CONFIRM_COUNT = 2        # 갭 확인 횟수

    # 시간 설정
    START_TIME = "08:30"         # 엔진 시작 (준비 단계)
    ENTRY_START_TIME = "09:00"   # 진입 시작 시간
    ENTRY_END_TIME = "09:03"     # 진입 종료 시간
    EOD_SELL_START = "15:15"     # EOD 청산 시작
    EOD_SELL_END = "15:28"       # EOD 청산 종료
    
    # 매수 스케줄 (HH:mm 리스트)
    BUY_SCHEDULE = ["09:00"]
    
    # Exit 조건 (청산)
    TAKE_PROFIT_RATE = 10.0      # 익절 기준 (%)
    STOP_LOSS_RATE = -3.0        # 손절 기준 (%)
    
    # 리스크 관리
    MAX_DAILY_LOSS_RATE = -5.0   # 일일 최대 손실률 (%)
    MAX_POSITIONS = 10           # 최대 동시 보유 종목 수
    
    # 주문 설정
    ORDER_SLIPPAGE_TICKS = 2     # 슬리피지 허용 틱수
    ORDER_TIMEOUT_SEC = 5        # 주문 타임아웃 (초)
    ORDER_RETRY_COUNT = 3        # 주문 재시도 횟수
    ORDER_RETRY_DELAY = 0.5      # 재시도 딜레이 (초)


# =============================
# 상태 머신 정의
# =============================
class PositionState(Enum):
    """종목별 전략 상태"""
    IDLE = "IDLE"                   # 미활성 상태
    WATCHING = "WATCHING"           # 감시 중 (매수 대기)
    ENTRY_PENDING = "ENTRY_PENDING" # 진입 주문 대기/접수
    ENTERED = "ENTERED"             # 보유 중
    EXIT_PENDING = "EXIT_PENDING"   # 청산 주문 대기/접수
    CLOSED = "CLOSED"               # 청산 완료
    SKIPPED = "SKIPPED"             # 건너뜀
    ERROR = "ERROR"                 # 오류 상태


class StrategyPhase(Enum):
    """전략 실행 단계 (개편된 상태머신)"""
    IDLE = "IDLE"                   # 비활성 (장외 시간)
    PREPARING = "PREPARING"         # 준비 단계 (08:30~첫 매수 전)
    ENTRY_WINDOW = "ENTRY_WINDOW"   # 진입 구간 (매매스케줄에 따른 매수 실행 중)
    MONITORING = "MONITORING"       # 장중 모니터링 (매수 완료 후 청산 감시)
    EOD_CLOSING = "EOD_CLOSING"     # 장마감 청산 (15:15~15:28)
    CLOSED = "CLOSED"               # 장 종료 (15:28 이후)


# =============================
# 데이터 클래스 정의
# =============================
@dataclass
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
    is_nxt: bool = False        # NXT 거래 가능 여부


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
    
    # 장치 정보
    is_nxt: bool = False        # NXT 거래 가능 여부
    
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
            'is_nxt': self.is_nxt,
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
        pos.is_nxt = data.get('is_nxt', False)
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
        self.state_file = Path(os.path.join(os.path.dirname(__file__), f"auto_trading_state{mode_suffix}.json"))
        
        # 초기화
        self._init_db()
        self._load_config_from_db()  # DB에서 설정 로드
        self._load_state()
    
    def _load_config_from_db(self):
        """DB(auto_trading_settings)에서 전략 설정 로드"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 'trading_strategy_config' 키로 시리얼라이즈된 JSON 로드
            cursor.execute("SELECT value FROM auto_trading_settings WHERE key = 'trading_strategy_config'")
            row = cursor.fetchone()
            conn.close()
            
            if row:
                config_data = json.loads(row[0])
                # StrategyConfig 인스턴스 업데이트 (UI의 TradingStrategyConfig 구조에 맞춤)
                
                # 1. 매수 스케줄 (buyTimeConfigs)
                if 'buyTimeConfigs' in config_data:
                    buy_schedule = []
                    for item in config_data['buyTimeConfigs']:
                        if item.get('enabled'):
                            buy_schedule.append(item.get('time'))
                    if buy_schedule:
                        self.config.BUY_SCHEDULE = buy_schedule
                
                # 2. 청산 조건 (sellConditions)
                if 'sellConditions' in config_data:
                    for item in config_data['sellConditions']:
                        if item.get('enabled'):
                            if item.get('type') == 'take_profit':
                                self.config.TAKE_PROFIT_RATE = float(item.get('value', 10.0))
                            elif item.get('type') == 'stop_loss':
                                # 손절은 음수로 저장 (UI는 보통 양수를 보여줄 수 있으므로 체크)
                                val = float(item.get('value', 3.0))
                                self.config.STOP_LOSS_RATE = -abs(val)
                
                # 3. 기타 설정
                if 'maxPositions' in config_data:
                    self.config.MAX_POSITIONS = int(config_data['maxPositions'])
                
                logger.info(f"DB에서 전략 설정 로드 완료: {config_data}")
            else:
                logger.info("DB에 전략 설정이 없어 기본 설정을 사용합니다.")
                
        except Exception as e:
            logger.error(f"전략 설정 로드 실패: {e}")

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
            token_file = Path(os.path.join(os.path.dirname(__file__), f"kis_token{token_suffix}.json"))
            if token_file.exists():
                with open(token_file, 'r') as f:
                    token_data = json.load(f)
                    # 'expired_time' 또는 'expiry' 키 모두 확인 (다른 스크립트 호환성)
                    expiry = token_data.get('expired_time') or token_data.get('expiry') or 0
                    if time.time() < expiry - 600:
                        self._access_token = token_data['access_token']
                        self._token_expired = expiry
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
                        'expired_time': self._token_expired,
                        'expiry': self._token_expired  # 호환성을 위해 둘 다 저장
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
                data = response.json()
                if isinstance(data, dict) and data.get('rt_cd') and data.get('rt_cd') != '0':
                    msg = data.get('msg1', 'API 오류')
                    self._log_event('ERROR', 'API_REJECT', f'API 요청 거부: {msg}', 
                                  data={'endpoint': endpoint, 'rt_cd': data.get('rt_cd'), 'msg_cd': data.get('msg_cd')})
                    return {'error': msg, 'detail': data}
                return data
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
    
    def _update_balance(self):
        """계좌 잔고 정보만 갱신 (전체 포지션 동기화 제외)"""
        balance = self._get_account_balance()
        if 'error' not in balance:
            # tot_evlu_amt(total_eval)와 nass_amt(available/net_asset) 중 큰 값을 총자산으로 간주
            # (휴장일이나 특정 상황에서 하나가 0으로 나올 수 있음)
            total_eval = balance.get('total_eval', 0)
            net_asset = balance.get('available', 0)
            
            self.state.total_asset = max(total_eval, net_asset)
            self.state.available_cash = balance.get('deposit', 0)  # 예수금을 매수 가능액으로 설정
            self._last_balance_check = time.time()
            return True
        return False

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
        
        if 'error' in result:
            return result
            
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
    
    # =============================
    # 유니버스 구축 (매매전략 설정 기반)
    # =============================
    
    def _load_universe_from_db(self) -> List[UniverseStock]:
        """서버 DB(auto_trading_target_stock)에서 등록된 종목을 로드하여 유니버스 구축"""
        self._log_event('INFO', 'UNIVERSE_LOAD', '서버 등록 종목 로드 시작')
        
        universe = []
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 서버 저장소(auto_trading_target_stock)에서 종목 조회
            cursor.execute("""
                SELECT code, name, base_price, market_cap, is_nxt FROM auto_trading_target_stock
            """)
            
            rows = cursor.fetchall()
            conn.close()
            
            for row in rows:
                code, name, base_price, market_cap, is_nxt = row
                
                universe.append(UniverseStock(
                    code=code,
                    name=name,
                    prev_close=base_price or 0.0,
                    prev_high=0.0,
                    change_rate=0.0,
                    market_cap=market_cap or 0.0,
                    added_date=self.state.today,
                    is_nxt=bool(is_nxt)
                ))
            
            self._log_event('INFO', 'UNIVERSE_COMPLETE', 
                          f'유니버스 로드 완료: {len(universe)}개 종목')
            
        except Exception as e:
            self._log_event('ERROR', 'UNIVERSE_ERROR', f'유니버스 로드 실패: {e}')
        
        return universe
            
    # =============================
    # 시그널 엔진 (매매전략 설정 기반)
    # =============================
    
    def check_entry_signal(self, position: Position) -> bool:
        """진입 시그널 확인: 현재 단계가 ENTRY_WINDOW이고 아직 매수하지 않았으면 True"""
        if self.state.phase == StrategyPhase.ENTRY_WINDOW and position.state == PositionState.WATCHING:
            return True
        return False
    
    def check_exit_signal(self, position: Position) -> Tuple[bool, str]:
        """청산 시그널 확인 (TP/SL/EOD)
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
            
            # TP 체크
            if pnl_rate >= self.config.TAKE_PROFIT_RATE:
                return True, "TP"
            
            # SL 체크
            if pnl_rate <= self.config.STOP_LOSS_RATE:
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
        """진입 주문 실행 (현재가 + 슬리피지 지정가 주문)"""
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
            if current_price <= 0:
                position.state = PositionState.SKIPPED
                position.error_message = '유효하지 않은 가격'
                return False
            
            # 주문가 결정: 현재가 + 슬리피지
            ask_price = price_data.get('ask_price')
            if not ask_price or ask_price <= 0:
                ask_price = current_price
            
            tick_size = self._get_tick_size(current_price)
            order_price = int(ask_price + (self.config.ORDER_SLIPPAGE_TICKS * tick_size))
            
            # 수량 계산
            quantity = int(position_amount / order_price)
            
            self._log_event('DEBUG', 'ENTRY_CALC', f'주문 계산 상세', 
                          code=position.code,
                          data={
                              'total_asset': self.state.total_asset,
                              'position_amount': position_amount,
                              'current_price': current_price,
                              'ask_price': ask_price,
                              'tick_size': tick_size,
                              'order_price': order_price,
                              'quantity': quantity
                          })
            
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
            result = self._place_order(position.code, quantity, 'buy', order_price)
            
            if 'error' in result:
                self._log_event('ERROR', 'ENTRY_FAIL', f'매수 주문 실패: {result["error"]}',
                              code=position.code)
                position.error_message = result['error']
                position.retry_count += 1
                
                if position.retry_count >= self.config.ORDER_RETRY_COUNT:
                    position.state = PositionState.SKIPPED
                return False
            
            order_id = result.get('order_no', '')
            if not order_id:
                self._log_event('ERROR', 'ENTRY_FAIL', '주문번호 누락 (API 응답 오류)',
                              code=position.code, data=result)
                position.state = PositionState.ERROR
                position.error_message = '주문번호 누락'
                return False

            position.order_id = order_id
            position.state = PositionState.ENTRY_PENDING
            position.pending_quantity = quantity
            position.order_time = datetime.now().isoformat()
            
            self._log_event('INFO', 'ENTRY_ORDER', f'매수 주문 접수',
                          code=position.code,
                          data={'order_no': position.order_id, 'qty': quantity, 'price': order_price})
            
            # ntfy 알림: 매수 주문 실행
            send_ntfy_notification(
                title="🚀 매수 주문 실행",
                message=f"[{position.name}] {quantity}주 @ {order_price:,}원 (지정가)",
                priority="default",
                tags=["rocket", "shopping_cart"]
            )
            
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
            
            # ntfy 알림: 매도 주문 실행
            reason_text = {
                'TP': '익절',
                'SL': '손절',
                'EOD': '장마감 청산',
                'MANUAL': '수동 청산'
            }.get(reason, reason)
            
            send_ntfy_notification(
                title=f"📢 {reason_text} 주문 실행",
                message=f"[{position.name}] {position.quantity}주 (시장가)",
                priority="default",
                tags=["loudspeaker", "outbox_tray"]
            )
            
            return True
        except Exception as e:
            self._log_event('ERROR', 'EXIT_ERROR', f'청산 실행 오류: {e}',
                          code=position.code)
            return False
    
    def confirm_order(self, position: Position) -> bool:
        """주문 체결 확인"""
        try:
            if not position.order_id:
                # 주문번호가 없는데 ENTRY_PENDING 이라면 비정상 상태이므로 WATCHING으로 복구
                if position.state == PositionState.ENTRY_PENDING:
                    self._log_event('WARNING', 'ORDER_ID_MISSING', 
                                  '주문번호 누락으로 인해 WATCHING 상태로 복구합니다.', code=position.code)
                    position.state = PositionState.WATCHING
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
                    pnl_type = "익절" if pnl >= 0 else "손절"
                    reason_text = {
                        'TP': '익절',
                        'SL': '손절', 
                        'EOD': f'장마감 청산 ({pnl_type})',
                        'MANUAL': f'수동 청산 ({pnl_type})'
                    }.get(position.exit_reason, f"{position.exit_reason} ({pnl_type})")
                    
                    send_ntfy_notification(
                        title=f"{emoji} {reason_text} 완료",
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
        """현재 시간에 따른 전략 단계 결정 (개편된 로직)"""
        now = datetime.now()
        current_time = now.strftime('%H:%M')
        
        # 1. 시작 전
        if current_time < self.config.START_TIME:
            return StrategyPhase.IDLE
            
        # 3. EOD 청산 구간
        if self.config.EOD_SELL_START <= current_time < self.config.EOD_SELL_END:
            return StrategyPhase.EOD_CLOSING
            
        # 4. 장 종료 후
        if current_time >= self.config.EOD_SELL_END:
            return StrategyPhase.CLOSED
            
        # 5. 진입(매수) 구간 확인
        # 설정된 BUY_SCHEDULE 중 현재 시간이 포함되는지 확인 (각 시간 기준 +3분간 유지)
        is_entry_window = False
        for scheduled_buy in self.config.BUY_SCHEDULE:
            buy_dt = datetime.strptime(scheduled_buy, '%H:%M')
            buy_end_dt = buy_dt + timedelta(minutes=3)
            buy_end_time = buy_end_dt.strftime('%H:%M')
            
            if scheduled_buy <= current_time < buy_end_time:
                is_entry_window = True
                break
        
        if is_entry_window:
            return StrategyPhase.ENTRY_WINDOW
            
        # 6. 준비 단계 vs 모니터링 단계
        # 첫 번째 매수 시간 이전이면 PREPARING, 이후면 MONITORING
        if self.config.BUY_SCHEDULE:
            first_buy = min(self.config.BUY_SCHEDULE)
            if current_time < first_buy:
                return StrategyPhase.PREPARING
            else:
                return StrategyPhase.MONITORING
        
        return StrategyPhase.MONITORING
    
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
        """준비 단계 (08:30~매수 시작 전)"""
        # 토큰 확인
        if not self._get_access_token():
            self._log_event('ERROR', 'PREPARE_FAIL', '토큰 발급 실패')
            return
        
        # 계좌 잔고 확인
        if not self._update_balance():
            self._log_event('ERROR', 'BALANCE_FAIL', '잔고 조회 실패 (API 오류)')
        
        # 미체결 주문 확인 (Restart 대응)
        for code, position in self.state.positions.items():
            if position.state in (PositionState.ENTRY_PENDING, PositionState.EXIT_PENDING):
                self.confirm_order(position)

        # 서버 등록 종목 로드 (아직 안했으면)
        if not self.state.universe:
            self.state.universe = self._load_universe_from_db()
            
            # 포지션 초기화
            for stock in self.state.universe:
                if stock.code not in self.state.positions:
                    self.state.positions[stock.code] = Position(
                        code=stock.code,
                        name=stock.name,
                        state=PositionState.WATCHING,
                        prev_close=stock.prev_close
                    )
            
            # ntfy 알림
            if self.state.universe:
                stock_list = ", ".join([s.name for s in self.state.universe[:10]])
                send_ntfy_notification(
                    title="🎯 자동매매 준비 완료 (서버 등록 종목)",
                    message=f"[{self.state.today}] 감시 종목 {len(self.state.universe)}개\n{stock_list}",
                    priority="default",
                    tags=["gear", "stock"]
                )
        
        time.sleep(5)
    
    def _phase_entry_window(self):
        """진입 구간 (BUY_SCHEDULE에 따른 매수 실행)"""
        for code, position in self.state.positions.items():
            if position.state == PositionState.WATCHING:
                # 진입 시그널 확인
                if self.check_entry_signal(position):
                    self.execute_entry(position)
            
            elif position.state == PositionState.ENTRY_PENDING:
                # 체결 확인
                self.confirm_order(position)
        
        time.sleep(0.5)
    
    def _phase_monitoring(self):
        """장중 모니터링 (청산 감시)"""
        for code, position in self.state.positions.items():
            # 미체결 매수 주문 확인
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
                # 대기 중인 모든 종목 건너뜀
                for position in self.state.positions.values():
                    if position.state == PositionState.WATCHING:
                        position.state = PositionState.SKIPPED
                        position.error_message = '일일 손실 한도 도달'
        
        time.sleep(1)
    
    def _phase_eod_closing(self):
        """장마감 청산 (15:15~15:28)"""
        for code, position in self.state.positions.items():
            if position.state == PositionState.ENTERED:
                self.execute_exit(position, "EOD")
            elif position.state == PositionState.EXIT_PENDING:
                self.confirm_order(position)
        
        time.sleep(1)
    
    def _phase_closed(self):
        """장 종료"""
        time.sleep(60)
    
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
        now = time.time()
        if not hasattr(self, '_last_balance_check') or now - self._last_balance_check > 60:
            try:
                self._update_balance()
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
            
            # ntfy 알림: 수동 매수 주문 실행
            send_ntfy_notification(
                title="🚀 수동 매수 주문 실행",
                message=f"[{code}] {quantity}주 (시장가)",
                priority="default",
                tags=["rocket", "shopping_cart", "mouse"]
            )
            
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
            
            # ntfy 알림: 수동 매도 주문 실행
            send_ntfy_notification(
                title="📢 수동 매도 주문 실행",
                message=f"[{position.name or code}] {sell_qty}주 (시장가)",
                priority="default",
                tags=["loudspeaker", "outbox_tray", "mouse"]
            )
            
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
            
            # 계좌 정보 업데이트 (최신화된 로직 적용)
            self._update_balance()
            
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


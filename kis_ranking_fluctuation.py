import os
import requests
import json
import time
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# KIS API 설정 (실전투자용)
APP_KEY = os.getenv("KIS_REAL_APP_KEY")
APP_SECRET = os.getenv("KIS_REAL_APP_SECRET")
BASE_URL = "https://openapi.koreainvestment.com:9443"
TOKEN_FILE = "kis_token_real.json"

def get_access_token():
    """접근 토큰 발급 (캐싱 포함)"""
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'r') as f:
            try:
                token_data = json.load(f)
                if token_data.get('expiry', 0) > time.time():
                    print("[Access Token] 캐시된 토큰 사용")
                    return token_data.get('access_token')
            except:
                pass

    url = f"{BASE_URL}/oauth2/tokenP"
    payload = {
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET
    }
    res = requests.post(url, data=json.dumps(payload))
    print(f"[Access Token] HTTP Status: {res.status_code}")
    res_data = res.json()
    if 'access_token' in res_data:
        print(f"[Access Token] 발급 성공")
        # 토큰 유효 기간 저장 (보통 24시간이나 안전하게 12시간으로 설정)
        token_data = {
            'access_token': res_data['access_token'],
            'expiry': time.time() + 12 * 3600
        }
        with open(TOKEN_FILE, 'w') as f:
            json.dump(token_data, f)
        return res_data.get('access_token')
    else:
        print(f"[Access Token] 실패 - Code: {res_data.get('error_code')}, Message: {res_data.get('error_description')}")
    return res_data.get('access_token')

def get_fluctuation_ranking(access_token):
    """국내주식 등락률 순위 조회"""
    url = f"{BASE_URL}/uapi/domestic-stock/v1/ranking/fluctuation"
    
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {access_token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "FHPST01700000",
        "custtype": "P",
    }
    
    params = {
        "fid_cond_mrkt_div_code": "J",
        "fid_cond_scr_div_code": "20171",
        "fid_input_iscd": "0000",
        "fid_rank_sort_cls_code": "0",
        "fid_input_cnt_1": "0",
        "fid_prc_cls_code": "1",
        "fid_input_price_1": "",
        "fid_input_price_2": "",
        "fid_vol_cnt": "",
        "fid_trgt_cls_code": "0",
        "fid_trgt_exls_cls_code": "0",
        "fid_div_cls_code": "0",
        "fid_rsfl_cls_code": "1"
    }
    
    res = requests.get(url, headers=headers, params=params)
    print(f"[Fluctuation Ranking] HTTP Status: {res.status_code}")
    print(f"[Fluctuation Ranking] Full Response: {res.text}")
    
    try:
        data = res.json()
        print(f"[Fluctuation Ranking] rt_cd: '{data.get('rt_cd')}', msg_cd: '{data.get('msg_cd')}', msg1: '{data.get('msg1')}'")
        return data
    except Exception as e:
        print(f"[Fluctuation Ranking] JSON 파싱 에러: {e}")
        return None

def get_current_price(access_token, symbol="005930"):
    """삼성전자 현재가 조회 (테스트용)"""
    url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price"
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {access_token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "FHKST01010100", # 현재가 조회용 실전투자 TR ID
    }
    params = {
        "fid_cond_mrkt_div_code": "J",
        "fid_input_iscd": symbol
    }
    res = requests.get(url, headers=headers, params=params)
    return res.json()

def get_volume_ranking(access_token):
    """국내주식 거래량 순위 조회 (테스트용)"""
    url = f"{BASE_URL}/uapi/domestic-stock/v1/ranking/volume"
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {access_token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "FHPST01710000",
    }
    params = {
        "fid_cond_mrkt_div_code": "J",
        "fid_cond_scr_div_code": "20171",
        "fid_input_iscd": "0000",
        "fid_rank_sort_cls_code": "0",
        "fid_input_cnt_1": "0",
        "fid_prc_cls_code": "1",
        "fid_input_price_1": "",
        "fid_input_price_2": "",
        "fid_vol_cnt": "",
        "fid_trgt_cls_code": "0",
        "fid_trgt_exls_cls_code": "0",
        "fid_div_cls_code": "0",
        "fid_rsfl_cls_code": "0"
    }
    res = requests.get(url, headers=headers, params=params)
    try:
        return res.json()
    except:
        return {"rt_cd": "ERROR", "msg1": f"HTTP {res.status_code}: 빈 응답"}

if __name__ == "__main__":
    print("--- KIS 실전투자 테스트 ---")
    
    token = get_access_token()
    if not token:
        print("토큰 발급 실패")
    else:
        print("토큰 발급 성공")
        
        print("\n1. 현재가 조회 테스트 (삼성전자 005930)")
        price_data = get_current_price(token)
        print(f"rt_cd: {price_data.get('rt_cd')}, msg_cd: {price_data.get('msg_cd')}, msg1: {price_data.get('msg1')}")
        
        print("\n2. 등락률 순위 조회 테스트")
        result = get_fluctuation_ranking(token)
        print(f"rt_cd: '{result.get('rt_cd')}', msg_cd: '{result.get('msg_cd')}', msg1: '{result.get('msg1')}'")
        
        print("\n3. 거래량 순위 조회 테스트")
        vol_result = get_volume_ranking(token)
        print(f"rt_cd: '{vol_result.get('rt_cd')}', msg_cd: '{vol_result.get('msg_cd')}', msg1: '{vol_result.get('msg1')}'")
        
        if result and result.get('rt_cd') == '0':
            print(f"\n조회 결과 (상위 20개):")
            print(f"{'순위':<4} | {'종목코드':<8} | {'종목명':<18} | {'현재가':>10} | {'전일대비':>8} | {'등락률':>8}%")
            print("-" * 80)
            
            output_list = result.get('output', [])
            for stock in output_list[:20]:
                rank = stock.get('data_rank', '-')
                code = stock.get('stck_shrn_iscd', '-')
                name = stock.get('hts_kor_isnm', '-')
                price = stock.get('stck_prpr', '0')
                diff = stock.get('prdy_vrss', '0')
                rate = stock.get('prdy_ctrt', '0.00')
                
                try:
                    price_val = f"{int(price):>10,}"
                    diff_val = f"{int(diff):>8,}"
                except:
                    price_val = f"{price:>10}"
                    diff_val = f"{diff:>8}"
                    
                print(f"{rank:<4} | {code:<8} | {name:<18} | {price_val} | {diff_val} | {rate:>8}%")
        else:
            if result:
                print(f"API 호출 에러: {result.get('msg1')} (Code: {result.get('rt_cd')})")
                if not result.get('rt_cd'):
                    print("서버에서 빈 응답을 반환했습니다. 파라미터나 계정 권한을 확인해주세요.")
            else:
                print("API 호출 결과가 없습니다.")

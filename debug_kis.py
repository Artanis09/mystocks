import json
import requests

APP_KEY = "PSM786MPoVa3UpQ0R51JEqEEGuldiY4JBvbs"
APP_SECRET = "6KPMpHh44nSTfvjYke2cyFz9Fiizmf5ip3Ih9QbYy7n29lpFIOgSai1V2YclrxJWU/RD9EyB24QCaweWQJMPelWrPd15fp399Fpk1ouzDWYDlbTijKMh90ALITQ+VLClrs6gVaGOpJWJ0lDlz/UR0CYc0KsqBPPhd4uoUCFJug1SRydO7KA="

def get_token():
    try:
        with open('kis_token.json', 'r') as f:
            return json.load(f)['access_token']
    except:
        return None

token = get_token()
url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-daily-price"
headers = {
    "content-type": "application/json; charset=utf-8",
    "authorization": f"Bearer {token}",
    "appkey": APP_KEY,
    "appsecret": APP_SECRET,
    "tr_id": "FHKST01010400",
    "custtype": "P"
}
params = {
    "fid_cond_mrkt_div_code": "J",
    "fid_input_iscd": "005930",
    "fid_org_adj_prc": "1",
    "fid_period_div_code": "D"
}

res = requests.get(url, headers=headers, params=params)
data = res.json()
print("Keys in output[0]:")
if "output" in data and len(data["output"]) > 0:
    print(data["output"][0].keys())
    print("\nExample data (first item):")
    print(json.dumps(data["output"][0], indent=2))
else:
    print(data)

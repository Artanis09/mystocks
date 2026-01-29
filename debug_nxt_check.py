import os
import sys
from dotenv import load_dotenv
load_dotenv()

# Add current directory to path
sys.path.append(os.getcwd())

from update_stock_prices import check_nxt_from_kis_api

def test():
    code = "005930" # Samsung Electronics
    print(f"Checking NXT for {code}...")
    result = check_nxt_from_kis_api(code)
    print(f"Result: {result}")

if __name__ == "__main__":
    test()

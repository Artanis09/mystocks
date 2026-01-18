import traceback
try:
    import update_stock_prices as mod
    print('import_ok')
except Exception:
    traceback.print_exc()

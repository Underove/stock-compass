import json
from unittest.mock import MagicMock, patch

def test_execute_tool_unknown():
    from app.tools import execute_tool
    result = execute_tool("nonexistent_tool", {}, "alice")
    assert "error" in result

def test_execute_get_stock_price():
    from app.tools import execute_tool
    fake_price = {"current_price": 65000, "change_pct": 1.5, "volume": 123456}
    with patch("app.tools._get_price", return_value=fake_price):
        result = execute_tool("get_stock_price", {"stock_code": "005930"}, "alice")
    assert result["current_price"] == 65000
    assert result["change_pct"] == 1.5

def test_execute_get_portfolio():
    from app.tools import execute_tool
    fake_items = [{"stock_code": "005930", "corp_name": "삼성전자", "buy_price": 60000, "quantity": 10}]
    fake_price = {"current_price": 65000, "change_pct": 1.2}
    with patch("app.tools._load_portfolio", return_value=fake_items), \
         patch("app.tools._get_price", return_value=fake_price):
        result = execute_tool("get_portfolio", {}, "alice")
    assert len(result["items"]) == 1
    assert result["items"][0]["corp_name"] == "삼성전자"

def test_execute_search_recent_news():
    from app.tools import execute_tool
    fake_news = [{"title": "삼성 호재", "description": "...", "url": "https://x.com", "date": "2026.05.26"}]
    with patch("app.tools._search_news", return_value=fake_news):
        result = execute_tool("search_recent_news", {"query": "삼성전자"}, "alice")
    assert len(result["items"]) == 1
    assert result["items"][0]["title"] == "삼성 호재"

def test_execute_get_technical_indicators():
    from app.tools import execute_tool
    fake_ta = {"rsi": 55.0, "macd": 1.2, "ma5": 60000, "ma20": 59000, "ma60": 58000, "current_price": 60500}
    with patch("app.tools._ta_analyze", return_value=fake_ta):
        result = execute_tool("get_technical_indicators", {"stock_code": "005930"}, "alice")
    assert result["rsi"] == 55.0

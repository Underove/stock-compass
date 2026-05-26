from unittest.mock import MagicMock, patch

def _make_text_response(text: str):
    part = MagicMock()
    part.function_call = None
    part.text = text
    candidate = MagicMock()
    candidate.content.parts = [part]
    resp = MagicMock()
    resp.candidates = [candidate]
    resp.text = text
    return resp

def _make_tool_then_text(fn_name: str, fn_args: dict, final_text: str):
    fn_part = MagicMock()
    fc = MagicMock()
    fc.name = fn_name
    fc.args = fn_args
    fn_part.function_call = fc
    fn_part.text = None

    candidate1 = MagicMock()
    candidate1.content.parts = [fn_part]
    candidate1.content.role = "model"
    resp1 = MagicMock()
    resp1.candidates = [candidate1]
    resp1.text = None

    resp2 = _make_text_response(final_text)
    return [resp1, resp2]

def test_generate_with_tools_text_only():
    from app.llm.gemini import generate_with_tools
    fake_resp = _make_text_response("삼성전자는 반도체 기업입니다.")
    with patch("app.llm.gemini.get_client") as mock_client:
        mock_client.return_value.models.generate_content.return_value = fake_resp
        with patch("app.llm.gemini.execute_tool") as mock_exec:
            result = generate_with_tools("삼성전자 소개해줘", username="alice")
    assert result == "삼성전자는 반도체 기업입니다."
    mock_exec.assert_not_called()

def test_generate_with_tools_one_tool_call():
    from app.llm.gemini import generate_with_tools
    responses = _make_tool_then_text(
        "get_stock_price", {"stock_code": "005930"}, "삼성전자 현재가는 65,000원입니다."
    )
    tool_result = {"current_price": 65000, "change_pct": 1.5}
    with patch("app.llm.gemini.get_client") as mock_client:
        mock_client.return_value.models.generate_content.side_effect = responses
        with patch("app.llm.gemini.execute_tool", return_value=tool_result) as mock_exec:
            result = generate_with_tools("삼성전자 주가 알려줘", username="alice")
    assert "65,000" in result or "65000" in result
    mock_exec.assert_called_once_with("get_stock_price", {"stock_code": "005930"}, "alice")

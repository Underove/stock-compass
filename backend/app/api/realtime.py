"""KIS 실시간 체결가 → 프론트엔드 WebSocket 프록시."""
import asyncio
import json

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.collectors.kis_ws import WS_URL, get_approval_key, parse_price, subscribe_msg
from app.config import settings

router = APIRouter()

_PINGPONG_RESP = json.dumps({"header": {"tr_id": "PINGPONG"}})


@router.websocket("/ws/realtime")
async def ws_realtime(ws: WebSocket):
    await ws.accept()

    if not settings.kis_app_key or not settings.kis_app_secret:
        await ws.send_json({"error": "KIS API 키가 설정되지 않았습니다."})
        await ws.close()
        return

    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=10)
        data = json.loads(raw)
        stock_codes: list[str] = data.get("subscribe", [])
    except Exception:
        await ws.close()
        return

    if not stock_codes:
        await ws.close()
        return

    try:
        approval_key = get_approval_key()
    except Exception as e:
        await ws.send_json({"error": f"KIS 인증 실패: {e}"})
        await ws.close()
        return

    try:
        async with websockets.connect(WS_URL, ping_interval=None) as kis_ws:
            for code in stock_codes:
                await kis_ws.send(subscribe_msg(approval_key, code))

            async for raw_msg in kis_ws:
                if isinstance(raw_msg, bytes):
                    raw_msg = raw_msg.decode("utf-8")

                # KIS PINGPONG 응답
                if "PINGPONG" in raw_msg:
                    await kis_ws.send(_PINGPONG_RESP)
                    continue

                price = parse_price(raw_msg)
                if price:
                    try:
                        await ws.send_json(price)
                    except WebSocketDisconnect:
                        return

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_json({"error": str(e)})
        except Exception:
            pass

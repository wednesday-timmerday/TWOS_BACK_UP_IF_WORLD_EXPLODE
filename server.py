# signaling_server.py
import asyncio
import json
from aiohttp import web, WSMsgType

# Structure: rooms[uid] = {"host": ws, "clients": set(ws)}
rooms = {}

async def ws_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    uid = None
    role = None

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except json.JSONDecodeError:
                    await ws.send_json({"type": "error", "error": "invalid_json"})
                    continue

                msg_type = data.get("type")

                # Registration
                if msg_type == "register":
                    uid = data.get("uid")
                    role = data.get("role")
                    if role not in ("host", "client") or not uid:
                        await ws.send_json({"type": "error", "error": "invalid_register"})
                        continue

                    if uid not in rooms:
                        rooms[uid] = {"host": None, "clients": set()}

                    if role == "host":
                        rooms[uid]["host"] = ws
                        print(f"[SIGNAL] Host registered: {uid}")
                        # notify existing clients if any
                        for client_ws in rooms[uid]["clients"]:
                            await client_ws.send_json({"type": "host-available", "uid": uid})
                    else:
                        rooms[uid]["clients"].add(ws)
                        print(f"[SIGNAL] Client registered: {uid}")
                        if rooms[uid]["host"]:
                            await rooms[uid]["host"].send_json({"type": "client-wants-join", "uid": uid})

                # Forward offers/answers/candidates
                elif msg_type in ("offer", "answer", "candidate"):
                    if not uid or uid not in rooms:
                        await ws.send_json({"type": "error", "error": "uid_not_found"})
                        continue
                    target = None
                    if role == "host":
                        # send to all clients
                        for client_ws in rooms[uid]["clients"]:
                            await client_ws.send_json(data)
                    else:
                        if rooms[uid]["host"]:
                            await rooms[uid]["host"].send_json(data)

                else:
                    await ws.send_json({"type": "error", "error": "unknown_type"})

            elif msg.type == WSMsgType.ERROR:
                print("ws connection error:", ws.exception())

    finally:
        # Cleanup on disconnect
        if uid and role and uid in rooms:
            if role == "host":
                # Notify all clients host disconnected
                for client_ws in rooms[uid]["clients"]:
                    try:
                        await client_ws.send_json({"type": "host-disconnected", "uid": uid})
                    except Exception:
                        pass
                rooms[uid]["host"] = None
                print(f"[SIGNAL] Host disconnected: {uid}")
            else:
                rooms[uid]["clients"].discard(ws)
                print(f"[SIGNAL] Client disconnected: {uid}")

    return ws

app = web.Application()
app.router.add_get("/", ws_handler)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=8765)

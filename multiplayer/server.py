"""
TWOS Multiplayer Server
-----------------------
Run:  python multiplayer/server.py
Clients connect to  ws://localhost:8765

Protocol (all JSON):
  client â†’ server:
    { "type": "join",  "room_id": "...", "uid": "...", "name": "..." }
    { "type": "state", "room_id": "...", "uid": "...", <player state> }
    { "type": "leave", "room_id": "...", "uid": "..." }

  server â†’ client:
    { "type": "joined",       "uid": "..." }               -- ack
    { "type": "player_join",  "uid": "...", "name": "..." } -- someone joined
    { "type": "player_state", <player state> }              -- position update
    { "type": "player_leave", "uid": "..." }               -- someone left
    { "type": "room_state",   "players": [...] }            -- full room dump on join
"""

import asyncio
import json
import websockets

# rooms[room_id] = { uid: {"ws": ws, "name": str, "state": dict} }
rooms: dict[str, dict] = {}


async def broadcast(room_id: str, message: dict, exclude_uid: str | None = None):
    """Send a message to every client in a room (optionally skip one)."""
    room = rooms.get(room_id, {})
    data = json.dumps(message)
    dead = []
    for uid, entry in room.items():
        if uid == exclude_uid:
            continue
        try:
            await entry["ws"].send(data)
        except Exception:
            dead.append(uid)
    for uid in dead:
        room.pop(uid, None)


async def handler(ws):
    uid = None
    room_id = None

    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            t = msg.get("type")

            # â”€â”€ JOIN â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            if t == "join":
                uid     = msg.get("uid", "")
                room_id = msg.get("room_id", "default")
                name    = msg.get("name", "???")

                if not room_id in rooms:
                    rooms[room_id] = {}

                # Tell the newcomer about everyone already in the room
                existing = [
                    {"uid": u, "name": e["name"], **e["state"]}
                    for u, e in rooms[room_id].items()
                ]
                await ws.send(json.dumps({"type": "room_state", "players": existing}))

                # Register them
                rooms[room_id][uid] = {"ws": ws, "name": name, "state": {}}

                # Ack back to them
                await ws.send(json.dumps({"type": "joined", "uid": uid}))

                # Announce to everyone else
                await broadcast(room_id, {"type": "player_join", "uid": uid, "name": name}, exclude_uid=uid)

                print(f"[JOIN]  room={room_id!r}  uid={uid[:8]}  name={name!r}  players={len(rooms[room_id])}")

            # â”€â”€ STATE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            elif t == "state":
                if uid is None or room_id is None:
                    continue
                room = rooms.get(room_id)
                if not room or uid not in room:
                    continue

                # Save latest state (everything except type/room_id/uid)
                state = {k: v for k, v in msg.items() if k not in ("type", "room_id")}
                room[uid]["state"] = state

                # Relay to others
                await broadcast(room_id, {"type": "player_state", **state}, exclude_uid=uid)

            # â”€â”€ LEAVE (clean disconnect message) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            elif t == "leave":
                break   # fall through to finally

    except websockets.exceptions.ConnectionClosedOK:
        pass
    except websockets.exceptions.ConnectionClosedError:
        pass
    except Exception as exc:
        print(f"[ERR] {exc}")
    finally:
        if uid and room_id and room_id in rooms:
            rooms[room_id].pop(uid, None)
            if not rooms[room_id]:
                del rooms[room_id]
            else:
                await broadcast(room_id, {"type": "player_leave", "uid": uid})
            print(f"[LEAVE] room={room_id!r}  uid={uid[:8] if uid else '?'}  remaining={len(rooms.get(room_id, {}))}")


async def main():
    print("=" * 40)
    print("  TWOS Multiplayer Server")
    print("  ws://localhost:8765")
    print("=" * 40)
    async with websockets.serve(handler, "0.0.0.0", 8765):
        await asyncio.Future()   # run forever


if __name__ == "__main__":
    asyncio.run(main())


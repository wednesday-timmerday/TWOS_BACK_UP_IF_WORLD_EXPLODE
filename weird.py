import time

import requests

from email.utils import parsedate_to_datetime

from pypresence import Presence, ActivityType



JELLYFIN_URL = "http://192.168.1.251:8096"

API_KEY = "e6cee7acc5bb4e17a123a21504ddce94"

DISCORD_CLIENT_ID = "1471411687595708530"

JELLYFIN_USER = "me"



headers = {"X-Emby-Token": API_KEY}



rpc = Presence(DISCORD_CLIENT_ID)

rpc.connect()



time_offset = 0

current_track_id = None

last_pause_state = None





def update_time_offset():

    global time_offset

    r = requests.get(f"{JELLYFIN_URL}/System/Info", headers=headers)

    server_date = r.headers.get("Date")



    if server_date:

        server_ts = int(parsedate_to_datetime(server_date).timestamp())

        local_ts = int(time.time())

        time_offset = server_ts - local_ts





def get_now_playing():

    url = f"{JELLYFIN_URL}/Sessions?ActiveWithinSeconds=10"

    r = requests.get(url, headers=headers)

    sessions = r.json()



    for session in sessions:

        if session.get("UserName") != JELLYFIN_USER:

            continue



        now_playing = session.get("NowPlayingItem")

        playstate = session.get("PlayState", {})



        if now_playing:

            track_id = now_playing.get("Id")

            artists = now_playing.get("Artists")

            artist_name = artists[0] if artists else "Unknown Artist"



            duration_ticks = now_playing.get("RunTimeTicks", 0)

            position_ticks = playstate.get("PositionTicks", 0)



            duration_seconds = duration_ticks / 10_000_000

            position_seconds = position_ticks / 10_000_000



            server_now = int(time.time() + time_offset)

            start_time = int(server_now - position_seconds)

            end_time = start_time + int(duration_seconds)



            return {

                "id": track_id,

                "title": now_playing.get("Name", "Unknown Title"),

                "artist": artist_name,

                "album": now_playing.get("Album", "Unknown Album"),

                "start_time": start_time,

                "end_time": end_time,

                "paused": playstate.get("IsPaused", False),

            }



    return None





print("Jellyfin Discord Rich Presence gestart...")

update_time_offset()



while True:

    try:

        now = get_now_playing()

        print(now)



        if now:

            if now["id"] != current_track_id or now["paused"] != last_pause_state:

                print("las")

                current_track_id = now["id"]

                last_pause_state = now["paused"]



                if now["paused"]:

                    rpc.update(

                        details=now["title"],

                        large_image="jellyfinlogo",

                        large_text="Paused",

                        activity_type=ActivityType.LISTENING,

                        buttons=[

                            {"label": "Cheese", "url": "https://cheese.com"}

                        ],

                    )

                else:

                    rpc.update(

                        details=now["title"],

                        large_image="jellyfinlogo",

                        large_text="Listening via Jellyfin",

                        activity_type=ActivityType.LISTENING,

                        start=now["start_time"],

                        end=now["end_time"],

                        buttons=[

                            {"label": "Cheese", "url": "https://cheese.com"}

                        ],

                    )

        else:

            if current_track_id is not None:

                rpc.clear()

                current_track_id = None

                last_pause_state = None



    except Exception as e:

        print("Fout:", e)



    time.sleep(0.75)


from flask import Flask, jsonify, render_template_string, request
import obsws_python as obs

app = Flask(__name__)

# =========================
# OBS SETTINGS
# =========================

OBS_HOST = "127.0.0.1"
OBS_PORT = 4455
OBS_PASSWORD = "lzDpINHwsuF1H2l2"


# =========================
# WEBSITE
# =========================

HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>OBS Control</title>

    <meta name="viewport" content="width=device-width, initial-scale=1">

    <style>
        body {
            margin: 0;
            background: #111;
            color: white;
            font-family: Arial, sans-serif;
            text-align: center;
        }

        .container {
            max-width: 600px;
            margin: auto;
            padding: 40px 20px;
        }

        h1 {
            font-size: 42px;
        }

        #status {
            font-size: 32px;
            margin: 30px 0;
        }

        button {
            width: 100%;
            padding: 22px;
            margin: 8px 0;
            font-size: 25px;
            font-weight: bold;
            border: none;
            border-radius: 15px;
            cursor: pointer;
        }

        #start {
            background: #e53935;
            color: white;
        }

        #stop {
            background: #333;
            color: white;
        }

        select {
            width: 100%;
            padding: 18px;
            font-size: 22px;
            border-radius: 12px;
            margin: 10px 0;
        }

        .section {
            margin-top: 35px;
            padding: 20px;
            background: #1b1b1b;
            border-radius: 15px;
        }

        .label {
            font-size: 20px;
            margin-bottom: 10px;
        }
    </style>
</head>

<body>

<div class="container">

    <h1>OBS CONTROL</h1>

    <div id="status">
        Checking OBS...
    </div>


    <!-- STREAM CONTROLS -->

    <div class="section">

        <button id="start" onclick="startStream()">
            GO LIVE
        </button>

        <button id="stop" onclick="stopStream()">
            END STREAM
        </button>

    </div>


    <!-- SCENE CONTROLS -->

    <div class="section">

        <div class="label">
            SWITCH SCENE
        </div>

        <select id="sceneSelect">
            <option>Loading scenes...</option>
        </select>

        <button onclick="switchScene()">
            SWITCH
        </button>

    </div>

</div>


<script>

async function startStream() {
    try {
        const response = await fetch("/start", {
            method: "POST"
        });

        const data = await response.json();

        if (!data.success) {
            alert("ERROR: " + data.error);
        }

        updateStatus();

    } catch (error) {
        alert("Could not contact server!");
    }
}


async function stopStream() {
    try {
        const response = await fetch("/stop", {
            method: "POST"
        });

        const data = await response.json();

        if (!data.success) {
            alert("ERROR: " + data.error);
        }

        updateStatus();

    } catch (error) {
        alert("Could not contact server!");
    }
}


async function updateStatus() {
    try {
        const response = await fetch("/status");
        const data = await response.json();

        if (data.streaming) {
            document.getElementById("status").innerHTML =
                "🔴 LIVE";
        } else {
            document.getElementById("status").innerHTML =
                "⚫ OFFLINE";
        }

    } catch (error) {
        document.getElementById("status").innerHTML =
            "❌ OBS NOT CONNECTED";
    }
}


// =========================
// GET OBS SCENES
// =========================

async function loadScenes() {

    try {

        const response = await fetch("/scenes");
        const data = await response.json();

        const select =
            document.getElementById("sceneSelect");

        select.innerHTML = "";

        if (!data.success) {
            select.innerHTML =
                "<option>OBS NOT CONNECTED</option>";

            return;
        }

        data.scenes.forEach(scene => {

            const option =
                document.createElement("option");

            option.value = scene;
            option.textContent = scene;

            select.appendChild(option);

        });

    } catch (error) {

        document.getElementById("sceneSelect").innerHTML =
            "<option>ERROR</option>";

    }
}


// =========================
// SWITCH SCENE
// =========================

async function switchScene() {

    const scene =
        document.getElementById("sceneSelect").value;

    if (!scene) {
        return;
    }

    try {

        const response = await fetch("/scene", {

            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({
                scene: scene
            })

        });

        const data = await response.json();

        if (!data.success) {

            alert(
                "ERROR: " +
                data.error
            );

        }

    } catch (error) {

        alert(
            "Could not contact server!"
        );

    }
}


// =========================
// START
// =========================

updateStatus();
loadScenes();


// Refresh status every 3 seconds
setInterval(updateStatus, 3000);


// Refresh scene list every 10 seconds
setInterval(loadScenes, 10000);

</script>

</body>
</html>
"""


# =========================
# OBS CONNECTION
# =========================

def get_obs():

    return obs.ReqClient(
        host=OBS_HOST,
        port=OBS_PORT,
        password=OBS_PASSWORD
    )


# =========================
# HOME PAGE
# =========================

@app.route("/")
def home():

    return render_template_string(HTML)


# =========================
# START STREAM
# =========================

@app.post("/start")
def start_stream():

    try:

        client = get_obs()

        client.start_stream()

        return jsonify({
            "success": True
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# =========================
# STOP STREAM
# =========================

@app.post("/stop")
def stop_stream():

    try:

        client = get_obs()

        client.stop_stream()

        return jsonify({
            "success": True
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# =========================
# STREAM STATUS
# =========================

@app.get("/status")
def stream_status():

    try:

        client = get_obs()

        status = client.get_stream_status()

        return jsonify({
            "streaming": status.output_active
        })

    except Exception as e:

        return jsonify({
            "streaming": False,
            "error": str(e)
        })


# =========================
# GET SCENES
# =========================

@app.get("/scenes")
def get_scenes():

    try:

        client = get_obs()

        result = client.get_scene_list()

        scenes = [
            scene["sceneName"]
            for scene in result.scenes
        ]

        return jsonify({
            "success": True,
            "scenes": scenes
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "error": str(e)
        })


# =========================
# SWITCH SCENE
# =========================

@app.post("/scene")
def switch_scene():

    try:

        data = request.get_json()

        scene_name = data["scene"]

        client = get_obs()

        client.set_current_program_scene(
            scene_name
        )

        return jsonify({
            "success": True
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# =========================
# START SERVER
# =========================

if __name__ == "__main__":

    print("")
    print("===================================")
    print("        OBS CONTROL SERVER")
    print("===================================")
    print("")
    print("Open: http://localhost:3000")
    print("")
    print("Press CTRL+C to stop.")
    print("")

    app.run(
        host="0.0.0.0",
        port=3000
    )
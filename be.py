import sounddevice as sd
import numpy as np
from scipy.signal import butter, lfilter
import time

# =====================
# CONFIG
# =====================
fs = 44100
threshold = 0.005
tolerance = 0.08

DEVICE = 23  # 🎯 CABLE Output (VB-Audio Virtual Cable)

# debounce (sneller voor sticks)
min_gap_sec = 0.12
min_gap_samples = int(min_gap_sec * fs)

# =====================
# FILTER (voor tikken)
# =====================
def bandpass(data, low=2000, high=8000, fs=44100):
    b, a = butter(3, [low/(fs/2), high/(fs/2)], btype='band')
    return lfilter(b, a, data)

# =====================
# STATE
# =====================
last_peak_sample = -min_gap_samples
global_sample_index = 0

tap_times = []
bpm = None
avg_interval = None
start_time = None

# =====================
# CALLBACK
# =====================
def audio_callback(indata, frames, time_info, status):
    global last_peak_sample, global_sample_index
    global tap_times, bpm, avg_interval, start_time

    # 🎯 stereo → mono
    audio = np.mean(indata, axis=1)

    # filter
    filtered = bandpass(audio)

    # envelope
    envelope = np.abs(filtered)

    # snelle smoothing
    envelope = np.convolve(envelope, np.ones(20)/20, mode='same')

    # adaptive threshold
    dynamic_threshold = max(threshold, np.mean(envelope) * 4)

    for i in range(1, len(envelope)-1):
        sample_index = global_sample_index + i

        if (
            envelope[i] > dynamic_threshold
            and envelope[i] > envelope[i-1]
            and envelope[i] > envelope[i+1]
        ):
            if sample_index - last_peak_sample > min_gap_samples:
                last_peak_sample = sample_index

                t = sample_index / fs
                tap_times.append(t)

                print(f"🥢 Tik @ {t:.3f}s")

                # ===== BPM LEARN =====
                if len(tap_times) == 4:
                    intervals = np.diff(tap_times[:4])
                    avg_interval = np.mean(intervals)
                    bpm = 60 / avg_interval
                    start_time = tap_times[0]

                    print(f"\n🔥 BPM DETECTED: {bpm:.2f}\n")

                # ===== LIVE TRACK =====
                elif bpm is not None:
                    beat_index = round((t - start_time) / avg_interval)
                    predicted = start_time + beat_index * avg_interval

                    if abs(t - predicted) < tolerance:
                        print(f"🥁 Beat {beat_index} ✅")
                    else:
                        print(f"⚠️ Off-beat ({t - predicted:.3f}s)")

    global_sample_index += frames

# =====================
# START
# =====================
print("🎧 Luisteren naar systeem-audio via VB-Cable...")
print("👉 Zorg dat je app geluid naar VB-Cable stuurt!")

with sd.InputStream(
    device=DEVICE,
    samplerate=fs,
    channels=2,
    callback=audio_callback,
    blocksize=1024
):
    while True:
        time.sleep(0.1)
"""
=============================================================================
 Realtime Desktop Audio Analyzer â€” BPM & Nootwaarde Detectie
=============================================================================
 Vereisten:
   pip install sounddevice numpy scipy matplotlib

 Gebruik:
   python audio_analyzer.py
=============================================================================
"""

import time
import threading
import collections
import sys

import numpy as np
import sounddevice as sd
from scipy.signal import butter, sosfilt

try:
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt
    import matplotlib.animation as animation
    VISUALIZE = True
except ImportError:
    VISUALIZE = False


# =============================================================================
#  CONFIGURATIE
# =============================================================================

SAMPLE_RATE       = 44100
BLOCK_SIZE        = 512    # kleinere blokken = snellere reactie
CHANNELS          = 2

THRESHOLD         = 0.003  # verlaag als er geen peaks komen, verhoog bij te veel

# EMA smoothing â€” hoger = sneller reageren op aanvallen
SMOOTH_ALPHA      = 0.40

# Minimale tijd tussen twee opeenvolgende peaks (debounce)
# Op 160 BPM is een kwartnoot 375ms, achtste noot 187ms
# Zet dit op de kleinste nootwaarde die je wil detecteren
MIN_PEAK_DIST_S   = 0.10   # 100ms = max ~600 BPM, voldoende fijn

# Kalibratie: hoeveel peaks voor de initiÃ«le BPM
CALIBRATION_PEAKS = 8      # meer peaks = stabielere eerste BPM-schatting

# Na kalibratie: BPM mag per stap max X% veranderen (drift-begrenzing)
BPM_MAX_DRIFT     = 0.08   # 8% per beat

BPM_HISTORY_LEN   = 16
NOTE_TOLERANCE    = 0.20

WAVEFORM_SAMPLES  = SAMPLE_RATE * 2

DEBUG_AMPLITUDE   = True
DEBUG_INTERVAL_S  = 0.3


# =============================================================================
#  HULPKLASSE: ThreadSafe RingBuffer
# =============================================================================

class RingBuffer:
    def __init__(self, max_len: int):
        self._buf  = collections.deque(maxlen=max_len)
        self._lock = threading.Lock()

    def extend(self, data: np.ndarray):
        with self._lock:
            self._buf.extend(data)

    def snapshot(self) -> np.ndarray:
        with self._lock:
            return np.array(self._buf, dtype=np.float32)


# =============================================================================
#  KERNKLASSE: AudioAnalyzer
# =============================================================================

class AudioAnalyzer:

    # Nootwaarden in beats (relatief t.o.v. Ã©Ã©n kwartnoot = 1 beat)
    NOTE_TABLE = {
        "32e noot":     0.125,
        "16e noot":     0.25,
        "achtste noot": 0.5,
        "kwartnoot":    1.0,
        "halve noot":   2.0,
        "hele noot":    4.0,
        "dubbele hele": 8.0,
    }

    def __init__(self):
        self.envelope         = 0.0
        self.last_peak_time   = 0.0
        self.peak_times       = []      # alle raw peak-tijden (voor kalibratie)
        self.calibrated       = False

        # Beat-grid state
        self.beat_duration_s  = None   # duur van Ã©Ã©n kwartnoot in seconden
        self.bpm              = None
        self.bpm_history      = collections.deque(maxlen=BPM_HISTORY_LEN)

        # Laatste geaccepteerde beat-tijd (voor nootduur-meting)
        self.last_beat_time   = None

        self.peak_marker_buf  = collections.deque(maxlen=100)
        self.waveform         = RingBuffer(WAVEFORM_SAMPLES)
        self._lock            = threading.Lock()

        # Bandpass filter
        self.sos = butter(2, [80, 4000], btype="band", fs=SAMPLE_RATE, output="sos")

        # Debug
        self._last_debug_print = 0.0
        self._max_raw_seen     = 0.0

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    #  Signaalverwerking
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _to_mono(self, block: np.ndarray) -> np.ndarray:
        return block.mean(axis=1) if block.ndim > 1 else block

    def _rms(self, signal: np.ndarray) -> float:
        return float(np.sqrt(np.mean(signal ** 2)))

    def _smooth(self, new_val: float) -> float:
        self.envelope = SMOOTH_ALPHA * new_val + (1.0 - SMOOTH_ALPHA) * self.envelope
        return self.envelope

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    #  BPM kalibratie & update
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _calibrate_bpm(self):
        """
        Gebruik mediaan van inter-onset intervals voor robuuste eerste schatting.
        Mediaan is minder gevoelig voor uitschieters dan gemiddelde.
        """
        intervals = np.diff(self.peak_times[:CALIBRATION_PEAKS])

        # Filter intervallen die te ver van de mediaan zitten (uitschieters weg)
        med = np.median(intervals)
        clean = intervals[np.abs(intervals - med) < med * 0.5]
        if len(clean) < 2:
            clean = intervals

        avg_ioi              = float(np.mean(clean))
        bpm_raw              = 60.0 / avg_ioi
        self.bpm_history.append(bpm_raw)
        self.beat_duration_s = avg_ioi
        self.bpm             = bpm_raw
        self.calibrated      = True
        self.last_beat_time  = self.peak_times[CALIBRATION_PEAKS - 1]

        print("\n" + "=" * 56, flush=True)
        print(f"  BPM GEKALIBREERD : {bpm_raw:.1f} BPM", flush=True)
        print(f"  Beat-duur        : {avg_ioi * 1000:.0f} ms", flush=True)
        print("=" * 56 + "\n", flush=True)

    def _update_bpm(self, measured_interval_s: float):
        """
        Pas BPM voorzichtig aan â€” maximaal BPM_MAX_DRIFT per stap.
        Zo drijft de BPM niet wild weg door ruis-peaks.
        """
        bpm_inst   = 60.0 / measured_interval_s
        max_change = self.bpm * BPM_MAX_DRIFT
        bpm_clamped = np.clip(bpm_inst,
                              self.bpm - max_change,
                              self.bpm + max_change)
        self.bpm_history.append(bpm_clamped)
        self.bpm             = float(np.mean(self.bpm_history))
        self.beat_duration_s = 60.0 / self.bpm

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    #  Nootclassificatie
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _classify_note(self, interval_s: float) -> str | None:
        """
        Classificeer interval als nootwaarde.
        Geeft None terug als het interval te klein is om muzikaal te zijn
        (kleiner dan een 32e noot).
        """
        beats      = interval_s / self.beat_duration_s
        min_beats  = min(self.NOTE_TABLE.values())

        # Negeer intervallen kleiner dan een 32e noot
        if beats < min_beats * (1 - NOTE_TOLERANCE):
            return None

        best_name  = "onbekend"
        best_delta = float("inf")
        for name, note_beats in self.NOTE_TABLE.items():
            delta = abs(beats - note_beats) / note_beats
            if delta < best_delta:
                best_delta = delta
                best_name  = name

        if best_delta > NOTE_TOLERANCE:
            return f"~{best_name} ({beats:.2f}x)"

        return best_name

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    #  Audio callback
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def process_block(self, indata: np.ndarray, frames: int, time_info, status):
        if status:
            print(f"[SD STATUS] {status}", file=sys.stderr, flush=True)

        now  = time.perf_counter()
        mono = self._to_mono(indata.copy())
        self.waveform.extend(mono)

        raw_rms  = self._rms(mono)
        filtered = sosfilt(self.sos, mono)
        filt_rms = self._rms(filtered)
        envelope = self._smooth(raw_rms)

        if raw_rms > self._max_raw_seen:
            self._max_raw_seen = raw_rms

        # â”€â”€ DEBUG output â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if DEBUG_AMPLITUDE and (now - self._last_debug_print >= DEBUG_INTERVAL_S):
            self._last_debug_print = now
            bar_len = 28
            fill    = min(int((envelope / max(THRESHOLD, 1e-9)) * bar_len), bar_len)
            bar     = "#" * fill + "." * (bar_len - fill)
            tag     = " <<< PEAK!" if envelope > THRESHOLD else ""
            print(
                f"[DEBUG]  raw={raw_rms:.5f}  env={envelope:.5f}"
                f"  thr={THRESHOLD:.5f}  [{bar}]{tag}",
                flush=True
            )

        # â”€â”€ Ruwe peak-detectie (debounce) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if envelope <= THRESHOLD:
            return
        if now - self.last_peak_time < MIN_PEAK_DIST_S:
            return

        # Peak geaccepteerd
        with self._lock:
            self.last_peak_time = now
            self.peak_times.append(now)
            self.peak_marker_buf.append(now)

        n = len(self.peak_times)

        # â”€â”€ Kalibratiefase â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if n < CALIBRATION_PEAKS:
            print(f"  [PEAK {n}/{CALIBRATION_PEAKS}]  kalibreren...", flush=True)
            return

        if n == CALIBRATION_PEAKS and not self.calibrated:
            self._calibrate_bpm()
            return

        if not self.calibrated:
            return

        # â”€â”€ Analysefase: meet interval t.o.v. vorige geaccepteerde beat â”€â”€â”€â”€â”€â”€â”€â”€
        interval = now - self.last_beat_time

        # Bereken verwachte nootduren (in seconden) voor context
        expected_quarter = self.beat_duration_s        # kwartnoot
        expected_eighth  = self.beat_duration_s * 0.5  # achtste noot
        smallest_valid   = self.beat_duration_s * 0.10 # 10% van beat = ruis-grens

        # Gooi peaks weg die te snel na de vorige komen (ruis / harmonic)
        if interval < smallest_valid:
            return

        # Classificeer
        note = self._classify_note(interval)
        if note is None:
            return  # te klein om te classificeren

        # Update BPM op basis van kwartnoot-intervallen (meest betrouwbaar)
        beats_measured = interval / self.beat_duration_s
        if 0.8 < beats_measured < 1.2:
            # Dit is een kwartnoot â€” gebruik hem voor BPM-update
            self._update_bpm(interval)
        elif 1.8 < beats_measured < 2.2:
            # Halve noot â€” deel door 2 voor beat-duur
            self._update_bpm(interval / 2)

        self.last_beat_time = now

        ms = int((now % 1) * 1000)
        ts = time.strftime("%H:%M:%S") + f".{ms:03d}"
        print(
            f"  [{ts}]  {note:<20}"
            f"  {interval * 1000:5.0f}ms"
            f"  BPM={self.bpm:5.1f}",
            flush=True
        )


# =============================================================================
#  APPARAATDETECTIE
# =============================================================================

def find_loopback_device():
    devices  = sd.query_devices()
    hostapis = sd.query_hostapis()
    for i, dev in enumerate(devices):
        if dev["max_input_channels"] < 1:
            continue
        name  = dev["name"].lower()
        hname = hostapis[dev["hostapi"]]["name"].lower()
        if "wasapi" in hname and "loopback" in name:
            print(f"[INFO] WASAPI loopback: [{i}] {dev['name']}")
            return i
        if "monitor" in name:
            print(f"[INFO] PulseAudio monitor: [{i}] {dev['name']}")
            return i
        if any(k in name for k in ("blackhole", "soundflower")):
            print(f"[INFO] Loopback driver: [{i}] {dev['name']}")
            return i
    return None


def list_devices():
    print("\nBeschikbare invoerapparaten:")
    print("â”€" * 64)
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:
            api = sd.query_hostapis(dev["hostapi"])["name"]
            print(f"  [{i:2d}] {dev['name']}  ({api})")
    print("â”€" * 64)


# =============================================================================
#  VISUALISATIE
# =============================================================================

def start_visualization(analyzer: AudioAnalyzer):
    fig, (ax_wave, ax_env) = plt.subplots(
        2, 1, figsize=(11, 5),
        gridspec_kw={"height_ratios": [3, 1]}
    )
    fig.patch.set_facecolor("#0d1117")
    for ax in (ax_wave, ax_env):
        ax.set_facecolor("#161b22")
        ax.tick_params(colors="#8b949e")
        for spine in ax.spines.values():
            spine.set_edgecolor("#30363d")

    ax_wave.set_title("Waveform  (rood = geaccepteerde beat)", color="#c9d1d9", fontsize=10)
    ax_wave.set_ylim(-1, 1)
    ax_env.set_title("Envelop vs drempelwaarde", color="#c9d1d9", fontsize=10)

    line_wave, = ax_wave.plot([], [], color="#58a6ff", lw=0.7)
    line_env,  = ax_env.plot([], [], color="#3fb950", lw=1.2, label="envelop")
    ax_env.axhline(THRESHOLD, color="#ff7b72", lw=1.0,
                   linestyle="--", label=f"threshold={THRESHOLD}")
    ax_env.legend(loc="upper right", fontsize=8,
                  facecolor="#161b22", edgecolor="#30363d", labelcolor="#c9d1d9")

    vlines      = []
    env_history = collections.deque(maxlen=300)

    def update(_):
        wave = analyzer.waveform.snapshot()
        if not len(wave):
            return line_wave, line_env

        line_wave.set_data(np.arange(len(wave)), wave)
        ax_wave.set_xlim(0, len(wave))

        env_history.append(analyzer.envelope)
        line_env.set_data(np.arange(len(env_history)), list(env_history))
        ax_env.set_xlim(0, max(len(env_history), 1))
        cur_max = max(list(env_history) + [THRESHOLD * 1.5])
        ax_env.set_ylim(0, cur_max * 1.2)

        for vl in vlines:
            vl.remove()
        vlines.clear()
        now = time.perf_counter()
        with analyzer._lock:
            markers = list(analyzer.peak_marker_buf)
        for pt in markers:
            age = now - pt
            if age < 2.0:
                pos = int((2.0 - age) / 2.0 * len(wave))
                vl  = ax_wave.axvline(x=pos, color="#ff7b72",
                                      alpha=max(0.0, 1.0 - age * 0.6), lw=1.5)
                vlines.append(vl)

        return line_wave, line_env, *vlines

    ani = animation.FuncAnimation(fig, update, interval=50,
                                  blit=False, cache_frame_data=False)
    plt.tight_layout()
    plt.show()


# =============================================================================
#  HOOFDPROGRAMMA
# =============================================================================

def main():
    print("=" * 64)
    print("  Realtime Desktop Audio Analyzer")
    print("=" * 64)

    list_devices()
    device_id = find_loopback_device()

    if device_id is None:
        print("\n[WAARSCHUWING] Geen loopback gevonden.")
        print("Apparaatnummer (of Enter voor standaard): ", end="", flush=True)
        try:
            raw       = input().strip()
            device_id = int(raw) if raw else None
        except (ValueError, EOFError):
            device_id = None

    analyzer = AudioAnalyzer()

    print(f"\n[CONFIG] THRESHOLD       = {THRESHOLD}")
    print(f"[CONFIG] MIN_PEAK_DIST   = {MIN_PEAK_DIST_S * 1000:.0f} ms")
    print(f"[CONFIG] CALIBRATION     = {CALIBRATION_PEAKS} peaks")
    print(f"[CONFIG] BPM_MAX_DRIFT   = Â±{BPM_MAX_DRIFT*100:.0f}% per beat\n")
    print(f"Luisteren... wacht op {CALIBRATION_PEAKS} peaks voor BPM-kalibratie.")
    print("Ctrl+C om te stoppen.\n")

    stream = sd.InputStream(
        device     = device_id,
        channels   = CHANNELS,
        samplerate = SAMPLE_RATE,
        blocksize  = BLOCK_SIZE,
        dtype      = "float32",
        callback   = analyzer.process_block,
    )

    with stream:
        if VISUALIZE:
            start_visualization(analyzer)
        else:
            try:
                while True:
                    time.sleep(0.1)
            except KeyboardInterrupt:
                pass

    print(f"\n[RAPPORT] Max raw RMS    : {analyzer._max_raw_seen:.5f}")
    print(f"[RAPPORT] Threshold      : {THRESHOLD:.5f}")
    if analyzer._max_raw_seen > 0:
        print(f"[RAPPORT] Aanbevolen thr : {analyzer._max_raw_seen * 0.4:.5f}")
        if analyzer._max_raw_seen < THRESHOLD:
            print("          !! Signaal haalde threshold nooit â€” verlaag THRESHOLD !!")


if __name__ == "__main__":
    main()

"""
Zagon:
1. cd ui
2. pip install -r requirements.txt
3. python app.py
4. oodpri: http://localhost:5000
5. "Zazeni okolje" button
6. Watch: http://localhost:8080/ (put it side by side with attacker window for best experience :D)
"""

import os
import subprocess
import threading
from pathlib import Path
from queue import Queue, Empty
from flask import Flask, render_template, request, jsonify, Response

app = Flask(__name__)
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
_process = None
_log_queue = Queue()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/status")
def status():
    # napad tece ? (status) + kelko attackerjev je aktivnih ? + victim tece ?
    global _process
    running = _process is not None and _process.poll() is None

    # Prestejemo aktivne attacker containerje
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "label=com.docker.compose.service=attacker", "--filter", "status=running", "-q"],
            capture_output=True, text=True, timeout=5
        )
        count = len(result.stdout.strip().split('\n')) if result.stdout.strip() else 0
    except Exception:
        count = 0

    # victim tecee ?
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=victim", "--filter", "status=running", "-q"],
            capture_output=True, text=True, timeout=5
        )
        victim_up = bool(result.stdout.strip())
    except Exception:
        victim_up = False

    return jsonify({"running": running or count > 0, "attackers": count, "victim": victim_up})


@app.route("/start", methods=["POST"])
def start_attack():
    # zazene docker compose z naseme parametrame.
    global _process, _log_queue

    if _process is not None and _process.poll() is None:
        return jsonify({"error": "Napad ze tece. Najprej ustavi trenutnega."}), 400

    data = request.get_json()
    mode = data.get("mode", "http")
    duration = data.get("duration", "30")
    threads = data.get("threads", "100")
    conns = data.get("conns", "200")
    scale = int(data.get("scale", "1"))

    _log_queue = Queue()

    cmd = [
        "docker", "compose", "--profile", "attack",
        "up", "-d", "--build", "--no-recreate", "--scale", f"attacker={scale}",
    ]

    env = os.environ.copy()
    env["ATTACK_MODE"] = mode
    env["DURATION"] = str(duration)
    env["THREADS"] = str(threads)
    env["SLOWLORIS_CONNS"] = str(conns)

    _log_queue.put(f"Zaganjam {scale}x {mode} napad za {duration}s ...")

    _process = subprocess.Popen(
        cmd, cwd=PROJECT_ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        text=True,
    )

    # Attacker logs -> logs window (SAMO attacker logs)
    def _follow_attacker_logs():
        """Pocaka da se containerji zazenejo, potem streama samo relevantne loge."""
        import time
        time.sleep(5)
        try:
            proc = subprocess.Popen(
                ["docker", "compose", "--profile", "attack", "logs", "-f", "--tail", "50", "attacker"],
                cwd=PROJECT_ROOT, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, bufsize=1,
            )
            for line in iter(proc.stdout.readline, ''):
                if not line:
                    continue
                clean = line.rstrip('\n')
                if '[attacker]' in clean:
                    idx = clean.find('[attacker]')
                    _log_queue.put(clean[idx:])
                check = subprocess.run(
                    ["docker", "ps", "--filter", "label=com.docker.compose.service=attacker", "--filter", "status=running", "-q"],
                    capture_output=True, text=True, timeout=3
                )
                if not check.stdout.strip():
                    break
            proc.terminate()
        except Exception:
            pass
        _log_queue.put("Napad koncan.")

    threading.Thread(target=_follow_attacker_logs, daemon=True).start()

    return jsonify({"ok": True})


@app.route("/stop", methods=["POST"])
def stop_attack():
    global _process

    _log_queue.put("Ustavljam napad ...")

    subprocess.run(
        ["docker", "compose", "--profile", "attack", "down"],
        cwd=PROJECT_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    try:
        result = subprocess.run(
            ["docker", "ps", "-a", "--filter", "label=com.docker.compose.service=attacker", "-q"],
            capture_output=True, text=True, timeout=5
        )
        ids = result.stdout.strip().split('\n')
        for cid in ids:
            if cid:
                subprocess.run(["docker", "rm", "-f", cid],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    if _process is not None and _process.poll() is None:
        try:
            _process.terminate()
            _process.wait(timeout=5)
        except Exception:
            _process.kill()
    _process = None

    _log_queue.put("Napad ustavljen. Containerji pocisceni.")
    return jsonify({"ok": True})


@app.route("/infra", methods=["POST"])
def toggle_infra():
    # start ali pa ustavi victim + monitoring
    data = request.get_json()
    action = data.get("action", "up")

    if action == "up":
        _log_queue.put("Zaganjam victim + monitoring ...")
        subprocess.Popen(
            ["docker", "compose", "up", "--build", "-d"],
            cwd=PROJECT_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        _log_queue.put("Victim + monitoring zagnana.")
    else:
        _log_queue.put("Ustavljam vse ...")
        subprocess.run(
            ["docker", "compose", "--profile", "attack", "down", "--remove-orphans"],
            cwd=PROJECT_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        _log_queue.put("Vse ustavljeno.")

    return jsonify({"ok": True})


@app.route("/logs")
def logs():
    # SSE endpoint za "real-time" logs.
    def generate():
        while True:
            try:
                line = _log_queue.get(timeout=1)
                yield f"data: {line}\n\n"
            except Empty:
                yield ": heartbeat\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    print("DDoS Simulation — Control Panel")
    print("http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)





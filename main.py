#!/usr/bin/env python3
"""
Discord Voice Camper + Custom RPC Selfbot

Commands (only own account):
  .ping
  .voice [channel_id]
  .rpc
  .status <online|idle|dnd|invisible>
  .stop / .continue
  .restart / .exit
"""

import os
import threading
import logging
from time import sleep, time
from signal import signal, SIGINT
from sys import executable, argv
import atexit
from http.server import BaseHTTPRequestHandler, HTTPServer

from dotenv import load_dotenv
load_dotenv()

import discum
from requests import get as rget
from color import color
from menu import UI

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Env helpers ───────────────────────────────────────────────────────────────
def _env(key, default=""):
    return os.getenv(key, default).strip()

def _yn(key, default="YES"):
    return _env(key, default).upper() == "YES"

# ── Config ────────────────────────────────────────────────────────────────────
TOKEN         = _env("TOKEN")
VOICE_CHANNEL = _env("VOICE_CHANNEL_ID")
GUILD_ID      = _env("GUILD_ID")
STATUS        = _env("STATUS", "online").lower()
PREFIX        = _env("PREFIX", ".")

APPLICATION_ID    = _env("APPLICATION_ID")
RPC_TYPE          = int(_env("RPC_TYPE", "0"))
RPC_NAME          = _env("RPC_NAME")
RPC_DETAILS       = _env("RPC_DETAILS")
RPC_STATE         = _env("RPC_STATE")
RPC_LARGE_IMAGE   = _env("RPC_LARGE_IMAGE")
RPC_LARGE_TEXT    = _env("RPC_LARGE_TEXT")
RPC_SMALL_IMAGE   = _env("RPC_SMALL_IMAGE")
RPC_SMALL_TEXT    = _env("RPC_SMALL_TEXT")
RPC_SHOW_ELAPSED  = _yn("RPC_SHOW_ELAPSED", "YES")
RPC_END_TIMESTAMP = _env("RPC_END_TIMESTAMP")
RPC_BUTTON1_LABEL = _env("RPC_BUTTON1_LABEL")
RPC_BUTTON1_URL   = _env("RPC_BUTTON1_URL")
RPC_BUTTON2_LABEL = _env("RPC_BUTTON2_LABEL")
RPC_BUTTON2_URL   = _env("RPC_BUTTON2_URL")

ui = UI()

# ── Validate ──────────────────────────────────────────────────────────────────
_errs = []
if not TOKEN:         _errs.append("TOKEN missing")
if not VOICE_CHANNEL: _errs.append("VOICE_CHANNEL_ID missing")
if not GUILD_ID:      _errs.append("GUILD_ID missing")
if _errs:
    for e in _errs:
        ui.slowPrinting(f"{color.fail}[ERROR]{color.reset} {e}")
    raise SystemExit

# ── Verify token ──────────────────────────────────────────────────────────────
try:
    _r = rget(
        "https://discord.com/api/v9/users/@me",
        headers={"Authorization": TOKEN},
        timeout=10,
    )
    if not _r.ok:
        ui.slowPrinting(f"{color.fail}[ERROR]{color.reset} Invalid TOKEN (HTTP {_r.status_code})")
        raise SystemExit
except SystemExit:
    raise
except Exception as e:
    ui.slowPrinting(f"{color.fail}[ERROR]{color.reset} Network error: {e}")
    raise SystemExit

# ── Health server (Render) ────────────────────────────────────────────────────
def _start_health_server():
    port = int(_env("PORT", "10000"))
    class _H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
        def do_HEAD(self):
            self.send_response(200)
            self.end_headers()
        def log_message(self, *a): pass
    HTTPServer(("0.0.0.0", port), _H).serve_forever()

threading.Thread(target=_start_health_server, daemon=True, name="health").start()

# ── State ─────────────────────────────────────────────────────────────────────
start_time       = time()
in_voice         = False
my_user_id       = None
stopped          = False
current_voice_ch = VOICE_CHANNEL
_voice_lock      = threading.Lock()
_rejoining       = False          # debounce: chỉ 1 rejoin thread tồn tại cùng lúc

# ── Discord client ────────────────────────────────────────────────────────────
bot = discum.Client(token=TOKEN, log=False)

# ── Uptime ────────────────────────────────────────────────────────────────────
def uptime_str() -> str:
    elapsed = int(time() - start_time)
    h, r = divmod(elapsed, 3600)
    m, s = divmod(r, 60)
    return f"{h:02}:{m:02}:{s:02}"

# ── Build RPC payload ─────────────────────────────────────────────────────────
def build_activities() -> list:
    if not RPC_NAME:
        return []
    act: dict = {"name": RPC_NAME, "type": RPC_TYPE}
    if APPLICATION_ID:
        act["application_id"] = APPLICATION_ID
    if RPC_DETAILS:
        act["details"] = RPC_DETAILS
    if RPC_STATE:
        act["state"] = RPC_STATE

    ts: dict = {}
    if RPC_SHOW_ELAPSED:
        ts["start"] = int(start_time)
    if RPC_END_TIMESTAMP:
        try:
            ts["end"] = int(RPC_END_TIMESTAMP)
        except ValueError:
            logger.warning("RPC_END_TIMESTAMP phải là số nguyên Unix, bỏ qua")
    if ts:
        act["timestamps"] = ts

    assets: dict = {}
    if RPC_LARGE_IMAGE: assets["large_image"] = RPC_LARGE_IMAGE
    if RPC_LARGE_TEXT:  assets["large_text"]  = RPC_LARGE_TEXT
    if RPC_SMALL_IMAGE: assets["small_image"] = RPC_SMALL_IMAGE
    if RPC_SMALL_TEXT:  assets["small_text"]  = RPC_SMALL_TEXT
    if assets:
        act["assets"] = assets

    buttons = []
    if RPC_BUTTON1_LABEL and RPC_BUTTON1_URL:
        buttons.append({"label": RPC_BUTTON1_LABEL, "url": RPC_BUTTON1_URL})
    if RPC_BUTTON2_LABEL and RPC_BUTTON2_URL:
        buttons.append({"label": RPC_BUTTON2_LABEL, "url": RPC_BUTTON2_URL})
    if buttons:
        act["buttons"] = buttons

    return [act]

# ── Set presence ──────────────────────────────────────────────────────────────
# FIX 1: setStatus() cần đủ 4 args: status, activities, afk, since
# Code cũ chỉ truyền 2 → TypeError → bị catch silently → RPC không bao giờ hoạt động
def set_presence(status: str = STATUS) -> None:
    try:
        bot.gateway.request.setStatus(
            status=status,
            activities=build_activities(),
            afk=False,   # ← FIX: thiếu arg này
            since=0,     # ← FIX: thiếu arg này
        )
        logger.info(f"Presence pushed — status={status} rpc={RPC_NAME!r}")
    except Exception as e:
        logger.error(f"set_presence error: {e}")

# ── Join voice ────────────────────────────────────────────────────────────────
def join_voice(channel_id: str = None) -> None:
    global in_voice, current_voice_ch, _rejoining
    target = channel_id or current_voice_ch
    if not target:
        logger.error("join_voice: không có channel ID")
        _rejoining = False
        return
    with _voice_lock:
        try:
            bot.gateway.request.call(
                channelID=target,
                guildID=GUILD_ID,
                mute=True,
                deaf=True,
            )
            current_voice_ch = target
            in_voice = True
            logger.info(f"Joined voice {target}")
            ui.slowPrinting(
                f"{color.okgreen}[VOICE]{color.reset} Joined {target}"
                + (" (custom)" if target != VOICE_CHANNEL else "")
            )
        except Exception as e:
            in_voice = False
            logger.error(f"join_voice error: {e}")
        finally:
            _rejoining = False   # luôn reset dù thành công hay thất bại

# FIX 2: Không sleep() trong gateway callback thread
# Dispatch rejoin sang daemon thread riêng, có debounce để tránh cascade
def _schedule_rejoin(delay: float = 5.0, channel_id: str = None) -> None:
    global _rejoining
    if _rejoining:
        logger.debug("Rejoin đã được scheduled, bỏ qua")
        return
    _rejoining = True

    def _run():
        sleep(delay)
        join_voice(channel_id=channel_id)

    threading.Thread(target=_run, daemon=True, name="rejoin").start()

# ── Gateway: on ready ─────────────────────────────────────────────────────────
@bot.gateway.command
def on_ready(resp):
    global my_user_id
    if not resp.event.ready_supplemental:
        return
    try:
        user       = getattr(bot.gateway.session, "user", {}) or {}
        my_user_id = user.get("id")
        username   = user.get("username", "?")
        discrim    = user.get("discriminator", "0")

        TYPE_LABEL = {0:"Playing",1:"Streaming",2:"Listening to",3:"Watching",5:"Competing in"}

        ui.slowPrinting("══════════════════════════════════════")
        ui.slowPrinting(f"Logged in   : {color.okgreen}{username}#{discrim}{color.reset}")
        ui.slowPrinting(f"Voice CH    : {VOICE_CHANNEL}")
        ui.slowPrinting(f"Guild       : {GUILD_ID}")
        ui.slowPrinting(f"Status      : {STATUS}")
        if RPC_NAME:
            ui.slowPrinting(f"RPC         : {TYPE_LABEL.get(RPC_TYPE,'?')} {RPC_NAME}")
            if RPC_DETAILS:       ui.slowPrinting(f"  Details   : {RPC_DETAILS}")
            if RPC_STATE:         ui.slowPrinting(f"  State     : {RPC_STATE}")
            if RPC_LARGE_IMAGE:   ui.slowPrinting(f"  LargeImg  : {RPC_LARGE_IMAGE}")
            if RPC_SMALL_IMAGE:   ui.slowPrinting(f"  SmallImg  : {RPC_SMALL_IMAGE}")
            if RPC_BUTTON1_LABEL: ui.slowPrinting(f"  Button1   : {RPC_BUTTON1_LABEL}")
            if RPC_BUTTON2_LABEL: ui.slowPrinting(f"  Button2   : {RPC_BUTTON2_LABEL}")
        else:
            ui.slowPrinting("RPC         : (not set)")
        ui.slowPrinting(f"Prefix      : '{PREFIX}'")
        ui.slowPrinting("══════════════════════════════════════")

        sleep(1)
        set_presence()
        sleep(1)
        join_voice()

    except Exception as e:
        logger.error(f"on_ready error: {e}")

# ── Gateway: on resumed (session resume — không có READY_SUPPLEMENTAL) ────────
# FIX 5: Khi gateway reconnect bằng RESUME thay vì IDENTIFY, Discord gửi
# event RESUMED (t="RESUMED") thay vì READY_SUPPLEMENTAL.
# → on_ready không bao giờ fire → RPC và voice không được re-push.
# → Fix: handle RESUMED riêng để re-push presence + rejoin voice ngay.
@bot.gateway.command
def on_resumed(resp):
    if resp.raw.get("t") != "RESUMED":
        return
    try:
        logger.info("Session resumed — re-pushing presence + voice")
        ui.slowPrinting(f"{color.okcyan}[BOT]{color.reset} Session resumed — re-pushing RPC + voice")
        sleep(0.5)
        set_presence()
        sleep(0.5)
        join_voice()
    except Exception as e:
        logger.error(f"on_resumed error: {e}")

# ── Gateway: voice disconnect watch ───────────────────────────────────────────
@bot.gateway.command
def voice_watch(resp):
    # FIX 2 (cont): khai báo global ở đầu function, không trong if block
    global in_voice
    if stopped:
        return
    try:
        if resp.raw.get("t") != "VOICE_STATE_UPDATE":
            return
        d = resp.raw.get("d") or {}
        if d.get("user_id") != my_user_id:
            return

        channel = d.get("channel_id")

        if channel is None:
            # Bị kick / disconnect
            in_voice = False
            logger.warning("Voice disconnected — rejoining in 5s")
            ui.slowPrinting(f"{color.warning}[VOICE]{color.reset} Disconnected — rejoining in 5s...")
            _schedule_rejoin(delay=5.0)          # ← không sleep ở đây nữa

        elif channel != current_voice_ch:
            # Bị move sang channel khác — snap back
            in_voice = False
            logger.info(f"Moved to {channel}, snapping back to {current_voice_ch}")
            ui.slowPrinting(
                f"{color.warning}[VOICE]{color.reset} "
                f"Moved to {channel} — snapping back..."
            )
            _schedule_rejoin(delay=2.0)          # ← không sleep ở đây nữa

    except Exception as e:
        logger.error(f"voice_watch error: {e}")

# ── Gateway: control commands ─────────────────────────────────────────────────
@bot.gateway.command
def cmd_handler(resp):
    global stopped
    try:
        if not resp.event.message:
            return
        m = resp.parsed.auto()
        if not isinstance(m, dict):
            return

        session_user = getattr(bot.gateway.session, "user", {}) or {}
        my_id   = session_user.get("id")
        author  = (m.get("author") or {}).get("id")
        ch      = m.get("channel_id", "")
        content = (m.get("content") or "").strip()

        if not my_id or author != my_id:
            return
        if not content.startswith(PREFIX):
            return

        raw_cmd = content[len(PREFIX):].strip()
        cmd     = raw_cmd.lower()

        # .ping
        if cmd == "ping":
            state = "⏸️ STOPPED" if stopped else "▶️ running"
            try:
                bot.sendMessage(ch,
                    f"🟢 Uptime: `{uptime_str()}` | "
                    f"Voice: {'✅' if in_voice else '❌'} `{current_voice_ch}` | {state}"
                )
            except: pass

        # .voice [channel_id]
        elif cmd == "voice" or cmd.startswith("voice "):
            parts = raw_cmd.split()
            target_ch = parts[1] if len(parts) > 1 else None
            if target_ch:
                join_voice(channel_id=target_ch)
                try: bot.sendMessage(ch, f"✅ Joining `{target_ch}` (custom)")
                except: pass
            else:
                join_voice(channel_id=VOICE_CHANNEL)
                try: bot.sendMessage(ch, f"✅ Joining `{VOICE_CHANNEL}` (default)")
                except: pass

        # .rpc
        elif cmd == "rpc":
            set_presence()
            try: bot.sendMessage(ch, "✅ RPC refreshed")
            except: pass

        # .status <online|idle|dnd|invisible>
        elif cmd.startswith("status "):
            new_s = cmd.split(" ", 1)[1].strip()
            if new_s in ("online", "idle", "dnd", "invisible"):
                try:
                    # FIX 1 (cont): truyền đủ 4 args ở đây nữa
                    bot.gateway.request.setStatus(
                        status=new_s,
                        activities=build_activities(),
                        afk=False,
                        since=0,
                    )
                    ui.slowPrinting(f"{color.okblue}[RPC]{color.reset} Status → {new_s}")
                    try: bot.sendMessage(ch, f"✅ Status → `{new_s}`")
                    except: pass
                except Exception as e:
                    logger.error(f"status cmd: {e}")
            else:
                try: bot.sendMessage(ch, "❌ Valid: online / idle / dnd / invisible")
                except: pass

        # .stop
        elif cmd == "stop":
            if not stopped:
                stopped = True
                logger.info("Bot paused")
                ui.slowPrinting(f"{color.warning}[BOT]{color.reset} Paused")
                try: bot.sendMessage(ch, f"⏸️ Paused. `{PREFIX}continue` to resume.")
                except: pass
            else:
                try: bot.sendMessage(ch, "ℹ️ Already stopped.")
                except: pass

        # .continue
        elif cmd == "continue":
            if stopped:
                stopped = False
                logger.info("Bot resumed")
                ui.slowPrinting(f"{color.okcyan}[BOT]{color.reset} Resumed")
                set_presence()
                sleep(0.5)
                if not in_voice:
                    join_voice()
                try: bot.sendMessage(ch, "▶️ Resumed.")
                except: pass
            else:
                try: bot.sendMessage(ch, "ℹ️ Already running.")
                except: pass

        # .restart
        elif cmd == "restart":
            try: bot.sendMessage(ch, "🔄 Restarting...")
            except: pass
            sleep(1)
            from os import execl
            execl(executable, executable, *argv)

        # .exit
        elif cmd == "exit":
            try: bot.sendMessage(ch, "⛔ Stopping...")
            except: pass
            sleep(1)
            try: bot.gateway.close()
            except: pass
            import os as _os
            _os._exit(0)

    except Exception as e:
        logger.error(f"cmd_handler error: {e}")

# ── Keepalive thread ──────────────────────────────────────────────────────────
def _keepalive():
    """
    Re-push presence mỗi 4 phút (Discord drop status nếu không refresh).
    Check voice mỗi 8 phút.
    """
    p_tick = 0
    v_tick = 0
    while True:
        sleep(60)
        if stopped:
            continue

        p_tick += 1
        v_tick  += 1

        if p_tick >= 4:
            set_presence()
            p_tick = 0

        if v_tick >= 8:
            if not in_voice:
                logger.info("[keepalive] not in voice — scheduling rejoin")
                _schedule_rejoin(delay=1.0)
            v_tick = 0

threading.Thread(target=_keepalive, daemon=True, name="keepalive").start()

# ── Signal handler ────────────────────────────────────────────────────────────
_shutdown = threading.Event()

def _sig_handler(sig, frame):
    _shutdown.set()

signal(SIGINT, _sig_handler)

@atexit.register
def _on_exit():
    try: bot.gateway.close()
    except: pass
    logger.info("Exited cleanly")

# FIX 3: Patch initial presence vào IDENTIFY payload TRƯỚC khi connect
# → RPC hiện ngay khi connect, không cần chờ READY event set_presence()
# (tham khảo từ Discord-RPC-Selfbot: set presence trước khi login)
try:
    bot.gateway.auth["presence"] = {
        "status": STATUS,
        "since": 0,
        "activities": build_activities(),
        "afk": False,
    }
    logger.info("Initial presence patched into IDENTIFY payload")
except Exception as e:
    logger.warning(f"Could not patch initial presence: {e}")

# ── Run — FIX 4: outer retry loop, không bao giờ raise SystemExit ───────────
# discum's auto_reconnect=True đã có while loop bên trong cho Discord disconnects.
# Outer loop này handle các crash nặng hơn mà auto_reconnect không xử lý được.
# Sau _MAX_CRASHES lần, dùng execl để hard restart process (Render sẽ không thấy exit).
_MAX_CRASHES  = 10
_crash_count  = 0

from os import system as _sys, name as _name
_sys("cls" if _name == "nt" else "clear")
ui.logo()

while not _shutdown.is_set():
    try:
        logger.info(f"Gateway connecting (crash #{_crash_count})")
        bot.gateway.run(auto_reconnect=True)
        # run() trả về bình thường chỉ khi close() hoặc KeyboardInterrupt
        # Nếu _shutdown được set → thoát vòng lặp
        if not _shutdown.is_set():
            logger.warning("gateway.run() returned unexpectedly, retrying in 5s")
            in_voice = False
            sleep(5)
    except KeyboardInterrupt:
        break
    except Exception as e:
        _crash_count += 1
        # Exponential backoff: 10s, 20s, 40s, tối đa 60s
        delay = min(10 * (2 ** min(_crash_count - 1, 3)), 60)
        logger.error(f"Gateway crash #{_crash_count}: {e} — retry in {delay}s")
        in_voice = False
        _rejoining = False

        if _crash_count >= _MAX_CRASHES:
            logger.error(f"Quá {_MAX_CRASHES} crashes — hard restart process")
            from os import execl
            execl(executable, executable, *argv)

        sleep(delay)

#!/usr/bin/env python3
"""
Discord Voice Camper + Custom RPC Selfbot

Commands:
  .ping
  .voice [channel_id]
  .rpc
  .status <online|idle|dnd|invisible>
  .stop
  .continue
  .restart
  .exit
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

# ── Helpers ───────────────────────────────────────────────────────────
def _env(key, default=""):
    return os.getenv(key, default).strip()

def _yn(key, default="YES"):
    return _env(key, default).upper() == "YES"

# ── Config ─────────────────────────────────────────────────────────────
TOKEN         = _env("TOKEN")
VOICE_CHANNEL = _env("VOICE_CHANNEL_ID")
GUILD_ID      = _env("GUILD_ID")
STATUS        = _env("STATUS", "online").lower()
PREFIX        = _env("PREFIX", ".")

# ── RPC config ────────────────────────────────────────────────────────────────
APPLICATION_ID    = _env("APPLICATION_ID")
RPC_TYPE          = int(_env("RPC_TYPE", "0"))       # 0=Playing 2=Listening 3=Watching 5=Competing
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
_errors = []
if not TOKEN:         _errors.append("TOKEN missing")
if not VOICE_CHANNEL: _errors.append("VOICE_CHANNEL_ID missing")
if not GUILD_ID:      _errors.append("GUILD_ID missing")
if _errors:
    for e in _errors:
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
    ui.slowPrinting(f"{color.fail}[ERROR]{color.reset} Network error verifying token: {e}")
    raise SystemExit

# ── Health server ─────────────────────────────────────────
def _start_health_server():
    port = int(_env("PORT", "10000"))
    class _H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
        def log_message(self, *a): pass
    HTTPServer(("0.0.0.0", port), _H).serve_forever()

threading.Thread(target=_start_health_server, daemon=True, name="health").start()

# ── State ─────────────────────────────────────────────────────────────────────
start_time       = time()
in_voice         = False
my_user_id       = None
stopped          = False            # .stop / .continue toggle
current_voice_ch = VOICE_CHANNEL
_voice_lock      = threading.Lock()

# ── Discord client ────────────────────────────────────────────────────────────
bot = discum.Client(token=TOKEN, log=False)

# ── Uptime ────────────────────────────────────────────────────────────────────
def uptime_str() -> str:
    elapsed = int(time() - start_time)
    h, r = divmod(elapsed, 3600)
    m, s = divmod(r, 60)
    return f"{h:02}:{m:02}:{s:02}"

# ── Build RPC activity ────────────────────────────────────────────────────────
def build_activities() -> list:
    if not RPC_NAME:
        return []

    act = {
        "name": RPC_NAME,
        "type": RPC_TYPE,
    }

    if APPLICATION_ID:
        act["application_id"] = APPLICATION_ID

    if RPC_DETAILS:
        act["details"] = RPC_DETAILS
    if RPC_STATE:
        act["state"] = RPC_STATE

    # ── Timestamps ────────────────────────────────────────────────────────────
    ts = {}
    if RPC_SHOW_ELAPSED:
        ts["start"] = int(start_time)
    if RPC_END_TIMESTAMP:
        try:
            ts["end"] = int(RPC_END_TIMESTAMP)
        except ValueError:
            logger.warning("RPC_END_TIMESTAMP is not an integer, skip.")
    if ts:
        act["timestamps"] = ts

    # ── Assets ──────────────────────────────────────────────────────────
    assets = {}
    if RPC_LARGE_IMAGE: assets["large_image"] = RPC_LARGE_IMAGE
    if RPC_LARGE_TEXT:  assets["large_text"]  = RPC_LARGE_TEXT
    if RPC_SMALL_IMAGE: assets["small_image"] = RPC_SMALL_IMAGE
    if RPC_SMALL_TEXT:  assets["small_text"]  = RPC_SMALL_TEXT
    if assets:
        act["assets"] = assets

    # ── Buttons ────────────────────────────────────────────────────
    buttons = []
    if RPC_BUTTON1_LABEL and RPC_BUTTON1_URL:
        buttons.append({"label": RPC_BUTTON1_LABEL, "url": RPC_BUTTON1_URL})
    if RPC_BUTTON2_LABEL and RPC_BUTTON2_URL:
        buttons.append({"label": RPC_BUTTON2_LABEL, "url": RPC_BUTTON2_URL})
    if buttons:
        act["buttons"] = buttons

    return [act]

# ── Set presence ──────────────────────────────────────────────────────────────
def set_presence(status: str = STATUS) -> None:
    try:
        bot.gateway.request.setStatus(
            status=status,
            activities=build_activities(),
        )
        logger.info(f"Presence pushed — status={status} rpc={RPC_NAME!r}")
    except Exception as e:
        logger.error(f"set_presence error: {e}")

# ── Join voice ────────────────────────────────────────────────────────────────
def join_voice(channel_id: str = None) -> None:
    global in_voice, current_voice_ch
    target = channel_id or current_voice_ch
    if not target:
        logger.error("join_voice: There is no channel ID to join")
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
                f"{color.okgreen}[VOICE]{color.reset} "
                f"Joined {target}"
                + (" (custom)" if target != VOICE_CHANNEL else " (default)")
            )
        except Exception as e:
            in_voice = False
            logger.error(f"join_voice error: {e}")

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
            if RPC_DETAILS:     ui.slowPrinting(f"  Details   : {RPC_DETAILS}")
            if RPC_STATE:       ui.slowPrinting(f"  State     : {RPC_STATE}")
            if RPC_LARGE_IMAGE: ui.slowPrinting(f"  LargeImg  : {RPC_LARGE_IMAGE}")
            if RPC_SMALL_IMAGE: ui.slowPrinting(f"  SmallImg  : {RPC_SMALL_IMAGE}")
            if RPC_BUTTON1_LABEL: ui.slowPrinting(f"  Button1   : {RPC_BUTTON1_LABEL}")
            if RPC_BUTTON2_LABEL: ui.slowPrinting(f"  Button2   : {RPC_BUTTON2_LABEL}")
        else:
            ui.slowPrinting("RPC         : (not set)")
        ui.slowPrinting(f"Prefix      : '{PREFIX}'")
        ui.slowPrinting("══════════════════════════════════════")

        sleep(2)
        set_presence()
        sleep(1)
        join_voice()

    except Exception as e:
        logger.error(f"on_ready error: {e}")

# ── Gateway: voice disconnect watch ───────────────────────────────────────────
@bot.gateway.command
def voice_watch(resp):
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
            # kick / disconnect
            in_voice = False
            logger.warning("Voice disconnected — rejoining in 5s")
            ui.slowPrinting(f"{color.warning}[VOICE]{color.reset} Disconnected — rejoining in 5s...")
            sleep(5)
            join_voice()

        elif channel != current_voice_ch:
            # move
            in_voice = False
            logger.info(f"Moved to {channel}, snapping back to {current_voice_ch}")
            ui.slowPrinting(
                f"{color.warning}[VOICE]{color.reset} "
                f"Moved to {channel} — snapping back to {current_voice_ch}..."
            )
            sleep(2)
            join_voice()

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

        # ── .ping ─────────────────────────────────────────────────────────
        if cmd == "ping":
            state = "⏸️ STOPPED" if stopped else "▶️ running"
            msg = (
                f"🟢 Uptime: `{uptime_str()}` | "
                f"Voice: {'✅' if in_voice else '❌'} `{current_voice_ch}` | "
                f"{state}"
            )
            try: bot.sendMessage(ch, msg)
            except: pass

        # ── .voice [channel_id] ───────────────────────────────────────────
        elif cmd == "voice" or cmd.startswith("voice "):
            parts = raw_cmd.split()
            target_ch = parts[1] if len(parts) > 1 else None
            if target_ch:
                join_voice(channel_id=target_ch)
                try: bot.sendMessage(ch, f"✅ Joining voice `{target_ch}` (custom)")
                except: pass
            else:
                join_voice(channel_id=VOICE_CHANNEL)
                try: bot.sendMessage(ch, f"✅ Joining voice `{VOICE_CHANNEL}` (default)")
                except: pass

        # ── .rpc ──────────────────────────────────────────────────────────
        elif cmd == "rpc":
            set_presence()
            try: bot.sendMessage(ch, "✅ RPC refreshed")
            except: pass

        # ── .status <online|idle|dnd|invisible> ──────────────────────────
        elif cmd.startswith("status "):
            new_s = cmd.split(" ", 1)[1].strip()
            if new_s in ("online", "idle", "dnd", "invisible"):
                try:
                    bot.gateway.request.setStatus(
                        status=new_s,
                        activities=build_activities(),
                    )
                    ui.slowPrinting(f"{color.okblue}[RPC]{color.reset} Status → {new_s}")
                    try: bot.sendMessage(ch, f"✅ Status → `{new_s}`")
                    except: pass
                except Exception as e:
                    logger.error(f"status cmd: {e}")
            else:
                try: bot.sendMessage(ch, "❌ Valid values: online / idle / dnd / invisible")
                except: pass

        # ── .stop ─────────────────────────────────────────────────────────
        elif cmd == "stop":
            if not stopped:
                stopped = True
                logger.info("Bot paused via .stop")
                ui.slowPrinting(f"{color.warning}[BOT]{color.reset} Paused — voice auto-rejoin & keepalive disabled")
                try: bot.sendMessage(ch, f"⏸️ Paused. Voice auto-rejoin & presence keepalive OFF. Send `{PREFIX}continue` to resume.")
                except: pass
            else:
                try: bot.sendMessage(ch, "ℹ️ Already stopped.")
                except: pass

        # ── .continue ─────────────────────────────────────────────────────
        elif cmd == "continue":
            if stopped:
                stopped = False
                logger.info("Bot resumed via .continue")
                ui.slowPrinting(f"{color.okcyan}[BOT]{color.reset} Resumed")
                set_presence()
                sleep(0.5)
                if not in_voice:
                    join_voice()
                try: bot.sendMessage(ch, "▶️ Resumed — presence refreshed, voice rejoined.")
                except: pass
            else:
                try: bot.sendMessage(ch, "ℹ️ Already running.")
                except: pass

        # ── .restart ──────────────────────────────────────────────────────
        elif cmd == "restart":
            try: bot.sendMessage(ch, "🔄 Restarting...")
            except: pass
            sleep(1)
            from os import execl
            execl(executable, executable, *argv)

        # ── .exit ─────────────────────────────────────────────────────────
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
    presence_tick = 0
    voice_tick    = 0
    while True:
        sleep(60)
        if stopped:
            continue

        presence_tick += 1
        voice_tick    += 1

        if presence_tick >= 5:
            set_presence()
            presence_tick = 0

        if voice_tick >= 10:
            if not in_voice:
                logger.info("[keepalive] Not in voice — rejoining")
                join_voice()
            voice_tick = 0

threading.Thread(target=_keepalive, daemon=True, name="keepalive").start()

# ── Signal / exit ─────────────────────────────────────────────────────────────
signal(SIGINT, lambda s, f: (_ for _ in ()).throw(KeyboardInterrupt()))

@atexit.register
def _on_exit():
    try: bot.gateway.close()
    except: pass
    logger.info("Exited cleanly")

# ── Run ───────────────────────────────────────────────────────────────────────
from os import system as _sys, name as _name
_sys("cls" if _name == "nt" else "clear")
ui.logo()

try:
    bot.gateway.run(auto_reconnect=True)
except KeyboardInterrupt:
    pass
except Exception as e:
    logger.error(f"Gateway crashed: {e}")
    raise SystemExit

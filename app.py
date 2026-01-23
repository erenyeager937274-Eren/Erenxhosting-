import os
import time
import asyncio
import subprocess
import shutil
import threading

import psutil
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web
from dotenv import load_dotenv

# ================= CONFIG =================
load_dotenv()

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID"))

app = Client(
    "UniversalHoster",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

APPROVED_FILE = "approved.txt"
PREMIUM_FILE = "premium.txt"

os.makedirs("logs", exist_ok=True)
os.makedirs("bots", exist_ok=True)

# ================= HELPERS =================
def is_owner(uid):
    return uid == OWNER_ID

def is_approved(uid):
    if is_owner(uid):
        return True
    if not os.path.exists(APPROVED_FILE):
        return False
    return str(uid) in open(APPROVED_FILE).read().splitlines()

def slot_limit(uid):
    if uid == OWNER_ID:
        return 999
    if os.path.exists(PREMIUM_FILE) and str(uid) in open(PREMIUM_FILE).read():
        return 10
    return 2  # free

# ================= WEB (Render) =================
async def handle(request):
    return web.Response(text="Bot is Running")

async def start_web():
    app_web = web.Application()
    app_web.router.add_get("/", handle)
    runner = web.AppRunner(app_web)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

# ================= DEPLOY =================
@app.on_message(filters.command("deploy"))
async def deploy(_, m):
    uid = m.from_user.id
    if not is_approved(uid):
        return await m.reply("❌ Access denied")

    try:
        args = m.text.split(" ", 1)[1]
        repo, token = [x.strip() for x in args.split("|")]
    except:
        return await m.reply("❌ Use: /deploy repo_link | bot_token")

    # slot check
    count = 0
    for b in os.listdir("bots"):
        ownerf = f"bots/{b}/owner.txt"
        if os.path.exists(ownerf) and open(ownerf).read().strip() == str(uid):
            count += 1
    if count >= slot_limit(uid):
        return await m.reply("🚫 Slot limit reached")

    name = repo.split("/")[-1].replace(".git", "")
    path = f"bots/{name}"

    if os.path.exists(path):
        shutil.rmtree(path)

    await m.reply("📥 Cloning repo…")
    os.system(f"git clone {repo} {path}")

    with open(f"{path}/owner.txt", "w") as f:
        f.write(str(uid))

    with open(f"{path}/.env", "w") as f:
        f.write(f"BOT_TOKEN={token}\n")

    log = open(f"logs/{name}.log", "a")
    p = subprocess.Popen(
        ["python3", "main.py"],
        cwd=path,
        stdout=log,
        stderr=log
    )

    with open(f"{path}/pid.txt", "w") as f:
        f.write(str(p.pid))

    with open(f"{path}/info.txt", "w") as f:
        f.write(f"start={int(time.time())}\ncmd=python3 main.py\n")

    await m.reply(f"✅ **{name} deployed & running**")

# ================= STOP SINGLE =================
@app.on_message(filters.command("stop"))
async def stop(_, m):
    if not is_owner(m.from_user.id):
        return await m.reply("❌ Owner only")

    try:
        name = m.text.split(" ", 1)[1]
    except:
        return await m.reply("❌ Use: /stop bot_name")

    pidf = f"bots/{name}/pid.txt"
    if not os.path.exists(pidf):
        return await m.reply("❌ Bot not running")

    pid = int(open(pidf).read())
    os.kill(pid, 9)
    os.remove(pidf)
    await m.reply(f"⛔ {name} stopped")

# ================= STOP ALL =================
@app.on_message(filters.command("stopall") & filters.user(OWNER_ID))
async def stopall(_, m):
    stopped = 0
    for b in os.listdir("bots"):
        pidf = f"bots/{b}/pid.txt"
        if os.path.exists(pidf):
            try:
                os.kill(int(open(pidf).read()), 9)
                os.remove(pidf)
                stopped += 1
            except:
                pass
    await m.reply(f"⛔ Stopped {stopped} bots")

# ================= STATUS PANEL =================
@app.on_message(filters.command("status"))
async def status(_, m):
    if not is_approved(m.from_user.id):
        return await m.reply("❌ Access denied")

    running = []
    for b in os.listdir("bots"):
        if os.path.exists(f"bots/{b}/pid.txt"):
            running.append(b)

    text = "📊 **BOT STATUS PANEL**\n\n"
    if running:
        text += "🟢 **Running Bots:**\n"
        text += "\n".join([f"• {b}" for b in running])
    else:
        text += "🔴 No running bots"

    buttons = [[InlineKeyboardButton("🔄 Refresh", callback_data="refresh")]]
    await m.reply(text, reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex("refresh"))
async def refresh(_, q):
    await q.message.delete()
    await status(_, q.message)

# ================= DASHBOARD =================
@app.on_message(filters.command("dashboard"))
async def dashboard(_, m):
    uid = m.from_user.id
    bots = []

    for b in os.listdir("bots"):
        ownerf = f"bots/{b}/owner.txt"
        if os.path.exists(ownerf) and open(ownerf).read().strip() == str(uid):
            bots.append(b)

    if not bots:
        return await m.reply("📭 You have no bots")

    text = "📊 **YOUR DASHBOARD**\n\n"
    for b in bots:
        s = "🟢 Running" if os.path.exists(f"bots/{b}/pid.txt") else "🔴 Stopped"
        text += f"• **{b}** → {s}\n"

    await m.reply(text)

# ================= USAGE =================
@app.on_message(filters.command("usage"))
async def usage(_, m):
    if not is_owner(m.from_user.id):
        return await m.reply("❌ Owner only")

    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory()

    await m.reply(
        "📊 **SERVER USAGE**\n\n"
        f"🧠 CPU: {cpu}%\n"
        f"💾 RAM: {ram.used//1024//1024} / {ram.total//1024//1024} MB\n"
        f"📈 Usage: {ram.percent}%"
    )

# ================= LOGS =================
@app.on_message(filters.command("logs"))
async def logs(_, m):
    if not is_owner(m.from_user.id):
        return await m.reply("❌ Owner only")

    try:
        name = m.text.split(" ", 1)[1]
    except:
        return await m.reply("❌ Use: /logs botname")

    file = f"logs/{name}.log"
    if not os.path.exists(file):
        return await m.reply("❌ Log not found")

    await m.reply_document(file)

# ================= BROADCAST =================
@app.on_message(filters.command("broadcast") & filters.user(OWNER_ID))
async def broadcast(_, m):
    if not m.reply_to_message:
        return await m.reply("Reply to a message")

    if not os.path.exists(APPROVED_FILE):
        return await m.reply("No users")

    users = open(APPROVED_FILE).read().splitlines()
    sent = 0
    for u in users:
        try:
            await app.copy_message(int(u), m.chat.id, m.reply_to_message.id)
            sent += 1
        except:
            pass

    await m.reply(f"📢 Broadcast sent to {sent} users")

# ================= AUTO RESTART =================
def auto_restart():
    while True:
        for b in os.listdir("bots"):
            pidf = f"bots/{b}/pid.txt"
            if os.path.exists(pidf):
                pid = int(open(pidf).read())
                if not psutil.pid_exists(pid):
                    log = open(f"logs/{b}.log", "a")
                    p = subprocess.Popen(
                        ["python3", "main.py"],
                        cwd=f"bots/{b}",
                        stdout=log,
                        stderr=log
                    )
                    open(pidf, "w").write(str(p.pid))
        time.sleep(10)

# ================= START =================
async def main():
    await start_web()
    await app.start()
    threading.Thread(target=auto_restart, daemon=True).start()
    print("🔥 Manager Bot Live")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())

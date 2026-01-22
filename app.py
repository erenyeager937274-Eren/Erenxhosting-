import os
import shutil
import subprocess
import asyncio
import signal
from datetime import datetime

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web
from dotenv import load_dotenv

load_dotenv()

# ---------------- CONFIG ----------------
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

# ---------------- FILES ----------------
APPROVED_FILE = "approved.txt"
LOG_FILE = "logs/actions.log"


# ---------------- HELPERS ----------------
def is_owner(user_id):
    return user_id == OWNER_ID


def is_approved(user_id):
    if is_owner(user_id):
        return True
    if not os.path.exists(APPROVED_FILE):
        return False
    with open(APPROVED_FILE) as f:
        return str(user_id) in f.read().splitlines()


def log_action(text):
    os.makedirs("logs", exist_ok=True)
    t = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{t}] {text}\n")


# ---------------- WEB SERVER (RENDER) ----------------
async def handle(request):
    return web.Response(text="Manager Bot Running 🚀")


async def start_web_server():
    server = web.Application()
    server.router.add_get("/", handle)
    runner = web.AppRunner(server)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()


# ---------------- REQUEST ACCESS ----------------
@app.on_message(filters.command("request"))
async def request_access(client, message):
    user = message.from_user
    text = (
        "🔔 **New Access Request**\n\n"
        f"👤 Name: {user.first_name}\n"
        f"🆔 ID: `{user.id}`\n"
        f"🔗 Username: @{user.username}"
    )
    await client.send_message(OWNER_ID, text)
    await message.reply("✅ Request sent to owner")


# ---------------- APPROVE USER ----------------
@app.on_message(filters.command("approve") & filters.user(OWNER_ID))
async def approve_user(client, message):
    try:
        uid = message.text.split(" ", 1)[1]
    except:
        return await message.reply("❌ Use: /approve user_id")

    with open(APPROVED_FILE, "a") as f:
        f.write(uid + "\n")

    await message.reply(f"✅ User `{uid}` approved")
    log_action(f"[APPROVE] {uid}")


# ---------------- DEPLOY BOT ----------------
@app.on_message(filters.command("deploy"))
async def deploy_bot(client, message):
    user_id = message.from_user.id

    if not is_approved(user_id):
        return await message.reply("❌ Access denied. Use /request")

    try:
        args = message.text.split(" ", 1)[1]
        repo_url, bot_token = [x.strip() for x in args.split("|")]
    except:
        return await message.reply("❌ Use: /deploy repo_link | bot_token")

    repo_name = repo_url.split("/")[-1].replace(".git", "")
    path = f"bots/{repo_name}"

    msg = await message.reply(f"🚀 Deploying **{repo_name}**...")

    if os.path.exists(path):
        shutil.rmtree(path)

    os.system(f"git clone {repo_url} {path}")

    with open(f"{path}/.env", "w") as f:
        f.write(
            f"API_ID={API_ID}\n"
            f"API_HASH={API_HASH}\n"
            f"BOT_TOKEN={bot_token}\n"
        )

    subprocess.run(["pip", "install", "-r", f"{path}/requirements.txt"])

    log_file = open(f"{path}/logs.txt", "w")

    process = subprocess.Popen(
        ["python3", "app.py"],
        cwd=path,
        stdout=log_file,
        stderr=log_file
    )

    with open(f"{path}/pid.txt", "w") as p:
        p.write(str(process.pid))

    await msg.edit(f"✅ **{repo_name} deployed & running**")
    log_action(f"[DEPLOY] {user_id} -> {repo_name}")


# ---------------- STOP BOT (TEXT) ----------------
@app.on_message(filters.command("stop"))
async def stop_bot(client, message):
    user_id = message.from_user.id

    if not is_approved(user_id):
        return await message.reply("❌ Access denied")

    try:
        bot = message.text.split(" ", 1)[1]
    except:
        return await message.reply("❌ Use: /stop bot_name")

    pid_file = f"bots/{bot}/pid.txt"

    if not os.path.exists(pid_file):
        return await message.reply("❌ Bot running nahi hai")

    with open(pid_file) as f:
        pid = int(f.read())

    os.kill(pid, signal.SIGKILL)
    os.remove(pid_file)

    await message.reply(f"🛑 **{bot} bot band kar diya**")
    log_action(f"[STOP] by {user_id} -> {bot}")


# ---------------- STATUS WITH BUTTONS ----------------
@app.on_message(filters.command("status"))
async def status_panel(client, message):
    user_id = message.from_user.id

    if not is_approved(user_id):
        return await message.reply("❌ Access denied")

    bots_dir = "bots"
    running = []

    if os.path.exists(bots_dir):
        for bot in os.listdir(bots_dir):
            pid_file = f"{bots_dir}/{bot}/pid.txt"
            if os.path.exists(pid_file):
                try:
                    with open(pid_file) as f:
                        pid = int(f.read())
                    os.kill(pid, 0)
                    running.append(bot)
                except:
                    pass

    text = "📊 **BOT STATUS PANEL**\n\n"
    text += "🟢 **Running Bots:**\n"
    text += "\n".join([f"• `{b}`" for b in running]) if running else "• None"

    buttons = []
    for b in running:
        buttons.append([
            InlineKeyboardButton(
                f"⛔ Stop {b}",
                callback_data=f"force_stop:{b}"
            )
        ])

    buttons.append([
        InlineKeyboardButton("🔄 Refresh", callback_data="refresh")
    ])

    await message.reply(text, reply_markup=InlineKeyboardMarkup(buttons))
    log_action(f"[STATUS] viewed by {user_id}")


# ---------------- BUTTON HANDLER ----------------
@app.on_callback_query()
async def button_handler(client, callback):
    user_id = callback.from_user.id
    data = callback.data

    if data == "refresh":
        await callback.message.delete()
        await status_panel(client, callback.message)
        return await callback.answer("🔄 Refreshed")

    if data.startswith("force_stop:"):
        if not is_owner(user_id):
            return await callback.answer("❌ Only owner allowed", show_alert=True)

        bot = data.split(":", 1)[1]
        pid_file = f"bots/{bot}/pid.txt"

        if not os.path.exists(pid_file):
            return await callback.answer("❌ Already stopped", show_alert=True)

        with open(pid_file) as f:
            pid = int(f.read())

        os.kill(pid, signal.SIGKILL)
        os.remove(pid_file)

        log_action(f"[FORCE STOP] by {user_id} -> {bot}")

        await callback.answer(f"🛑 {bot} stopped")
        await callback.message.delete()
        await status_panel(client, callback.message)


# ---------------- START ----------------
async def main():
    await start_web_server()
    await app.start()
    print("🔥 Manager Bot is Live!")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())

import asyncio
import json
import logging
import os
import uuid
from urllib.parse import urlparse, quote
import requests
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

# Переменные из Koyeb
BOT_TOKEN = os.getenv("8500260860:AAEWeSSohk08cUEiUuilpVEeXgxf6CYOp9M")
PANEL_URL = os.getenv("https://88.210.63.146:4002/CO1iXWw9AaXieQMDjR", "").rstrip("/")  # Например: http://1.2.3.4:2053/mysecretpath
PANEL_USER = os.getenv("leA8VYSj6P")                # Логин от 3x-ui
PANEL_PASS = os.getenv("hBWrR9AwbT")                # Пароль от 3x-ui
INBOUND_ID = int(os.getenv("1", "1"))      # ID инбаунда (обычно 1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def create_vless_key(tg_user_id: int) -> str:
    session = requests.Session()
    
    # 1. Логинимся в 3x-ui
    login_resp = session.post(
        f"{PANEL_URL}/login",
        data={"username": PANEL_USER, "password": PANEL_PASS},
        verify=False,
        timeout=10
    )
    if not login_resp.ok or not login_resp.json().get("success"):
        raise Exception("Не удалось войти в 3x-ui. Проверь PANEL_URL, логин и пароль.")

    # 2. Получаем настройки инбаунда (чтобы достать pbk, sni, sid)
    inb_resp = session.get(f"{PANEL_URL}/panel/api/inbounds/get/{INBOUND_ID}", verify=False, timeout=10)
    inb_data = inb_resp.json().get("obj")
    if not inb_data:
        raise Exception(f"Инбаунд с ID {INBOUND_ID} не найден.")

    port = inb_data["port"]
    stream = json.loads(inb_data["streamSettings"])
    reality = stream["realitySettings"]
    pbk = reality["settings"]["publicKey"]
    sni = reality["serverNames"][0]
    sid = reality["shortIds"][0]

    # 3. Создаем нового клиента
    client_uuid = str(uuid.uuid4())
    email = f"tg_{tg_user_id}_{ str(uuid.uuid4())[:4] }"

    client_settings = {
        "clients": [{
            "id": client_uuid,
            "flow": "xtls-rprx-vision",
            "email": email,
            "limitIp": 2,
            "totalGB": 0,
            "expiryTime": 0,
            "enable": True,
            "tgId": str(tg_user_id),
            "subId": ""
        }]
    }

    add_resp = session.post(
        f"{PANEL_URL}/panel/api/inbounds/addClient",
        json={"id": INBOUND_ID, "settings": json.dumps(client_settings)},
        verify=False,
        timeout=10
    )
    if not add_resp.json().get("success"):
        raise Exception(f"Ошибка создания ключа: {add_resp.text}")

    # 4. Собираем готовую ссылку vless://
    server_ip = urlparse(PANEL_URL).hostname
    vless_link = (
        f"vless://{client_uuid}@{server_ip}:{port}"
        f"?type=tcp&security=reality&pbk={pbk}&fp=chrome&sni={sni}"
        f"&sid={sid}&spx=%2F&flow=xtls-rprx-vision#{quote(email)}"
    )
    return vless_link


@dp.message(Command("start"))
async def cmd_start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Получить ключ VPN", callback_data="get_key")]
    ])
    await message.answer("Здаров! Жми кнопку ниже, чтобы сгенерировать свой VLESS-ключ:", reply_markup=kb)


@dp.callback_query(F.data == "get_key")
async def process_get_key(callback: CallbackQuery):
    await callback.answer("Генерирую ключ...")
    try:
        link = await asyncio.to_thread(create_vless_key, callback.from_user.id)
        await callback.message.answer(
            f"Готово! Твой ключ (нажми, чтобы скопировать):\n\n`{link}`\n\n"
            f"Закидывай его в **v2rayNG**, **Hiddify** или **Streisand**.",
            parse_mode="Markdown"
        )
    except Exception as e:
        await callback.message.answer(f"Бля, вылезла ошибка:\n`{e}`", parse_mode="Markdown")


# Заглушка для Koyeb Health Check (чтобы бесплатный контейнер не умирал)
async def health_check(request):
    return web.Response(text="Bot is alive!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()


async def main():
    logging.basicConfig(level=logging.INFO)
    await start_web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
  

import asyncio
import argparse
import re
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

from app.core.config import SESSIONS_DIR

TARGET_URL = "https://chatgpt.com/"
DATA_DIR = SESSIONS_DIR


def sanitize_name(name: str) -> str:
    name = name.strip()
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"[^A-Za-z0-9_\-]", "", name)
    if not name:
        raise ValueError("Имя файла сессии после очистки пустое.")
    return name


async def save_storage_state(context, state_path: Path) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    await context.storage_state(path=str(state_path))


async def capture_session(
    name: str,
    url: str = TARGET_URL,
    headless: bool = False,
    slow_mo_ms: int = 50,
    timeout_ms: int = 120_000,
    user_agent: Optional[str] = None,
) -> Path:
    async with async_playwright() as p:
        print(f"\n🚀 Старт захвата сессии: {name}")
        browser = await p.chromium.launch(
            headless=headless,
            slow_mo=slow_mo_ms,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )

        context = await browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        try:
            print(f"🌐 Открываем {url}")
            await page.goto(url, timeout=timeout_ms, wait_until="load")

            print(
                "\nℹ️ Войдите в аккаунт в открывшемся окне."
                "\n   Когда закончите, нажмите Enter для сохранения сессии."
                "\n   Или введите 'q' и нажмите Enter, чтобы отменить."
            )
            user_input = input("> ")

            if user_input.strip().lower() == "q":
                print("🛑 Отменено пользователем, state не сохранён.")
                return Path()

            state_path = DATA_DIR / f"{name}.json"
            await save_storage_state(context, state_path)
            print(f"✅ Состояние сохранено: {state_path}")
            return state_path

        except PlaywrightTimeoutError as te:
            print(f"⛔ Таймаут при открытии {url}: {te}")
            raise
        except Exception as e:
            print(f"⛔ Неожиданная ошибка: {e}")
            raise
        finally:
            await browser.close()
            print("🧹 Браузер закрыт.")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Открыть ChatGPT, выполнить вход и сохранить storage state в JSON."
    )
    parser.add_argument(
        "name",
        nargs="?",
        help="Имя файла сессии (латиница/цифры/-, _). Если не указано — будет запрошено.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Запуск в headless-режиме (обычно неудобно для ручного входа).",
    )
    parser.add_argument(
        "--slowmo",
        type=int,
        default=50,
        help="Задержка между действиями в мс (по умолчанию 50).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120_000,
        help="Таймаут загрузки в мс (по умолчанию 120000).",
    )
    parser.add_argument(
        "--user-agent",
        type=str,
        default=None,
        help="Переопределить User-Agent (опционально).",
    )
    return parser


async def async_main():
    parser = build_arg_parser()
    args = parser.parse_args()

    name = args.name or input("Введите имя для файла сессии (латиница/цифры/-, _): ").strip()
    name = sanitize_name(name)

    try:
        saved = await capture_session(
            name=name,
            url=TARGET_URL,
            headless=args.headless,
            slow_mo_ms=args.slowmo,
            timeout_ms=args.timeout,
            user_agent=args.user_agent,
        )
        if saved:
            print("🎉 Готово!")
    except KeyboardInterrupt:
        print("\n🛑 Операция прервана пользователем.")


if __name__ == "__main__":
    asyncio.run(async_main())

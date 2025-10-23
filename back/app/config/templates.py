# templates.py
from typing import Tuple
import os

from dotenv import load_dotenv
load_dotenv()

CABINET_URL = os.getenv("CABINET_URL", "https://app.aeoagency.team/login")
TELEGRAM_URL = os.getenv("TELEGRAM_URL", "https://t.me/aeoagency_support")
PAY_URL = os.getenv("PAY_URL", "https://app.aeoagency.team/billing")
BRIEF_URL = os.getenv("BRIEF_URL", "https://app.aeoagency.team/brief-seo")

def tpl_report(email: str, project: str) -> Tuple[str, str]:
    subj = "Ваш отчёт и рекомендации по видимости"
    html = f"""
    <p>Здравствуйте!</p>
    <p>Мы подготовили отчёт по проекту <b>{project}</b> и рекомендации по росту видимости.</p>
    <p><a href="{CABINET_URL}">Перейти в кабинет</a> — там можно скачать PDF и посмотреть детали.</p>
    <hr>
    <p>Также в кабинете — быстрые кнопки: оплатить продвижение или связаться с AEO Agency.</p>
    """
    return subj, html

def tpl_remind_2d(email: str, project: str) -> Tuple[str, str]:
    subj = "Подсказать пакет продвижения?"
    html = f"""
    <p>Вы ещё не определились с пакетом для <b>{project}</b>.</p>
    <p>Напишите нам — подскажем оптимальный вариант под ваши цели.</p>
    <p><a href="{TELEGRAM_URL}">Открыть Telegram</a></p>
    """
    return subj, html

def tpl_cases_5d(email: str, project: str) -> Tuple[str, str]:
    subj = "Кейсы по росту видимости + быстрый старт"
    html = f"""
    <p>Поделились статьёй с примерами, как мы растим видимость брендов в ответах ИИ.</p>
    <p><a href="{PAY_URL}">Выбрать пакет и оплатить</a></p>
    """
    return subj, html

def tpl_brief_9d(email: str, project: str) -> Tuple[str, str]:
    subj = "Сделаем базовый SEO-анализ вашего сайта?"
    html = f"""
    <p>Хотите получить базовый SEO-анализ? Заполните короткий бриф — и мы пришлём рекомендации.</p>
    <p><a href="{BRIEF_URL}">Заполнить бриф</a></p>
    """
    return subj, html

def tpl_remind_23d(email: str, project: str) -> Tuple[str, str]:
    subj = "Напоминание про сервис AEO"
    html = f"""
    <p>Напоминаем: в кабинете доступны отчёты, рекомендации и запуск продвижения.</p>
    <p><a href="{CABINET_URL}">Перейти в кабинет</a></p>
    """
    return subj, html

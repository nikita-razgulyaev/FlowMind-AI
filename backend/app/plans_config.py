"""Единое место, где задаются тарифы, цены, лимиты и суточный потолок AI.

Меняйте значения ТОЛЬКО здесь. Всё остальное подтянется само:

* карточки тарифов (список «что входит») собираются из этих чисел;
* при старте сервиса значения синхронизируются с базой (см. seed.sync_plans);
* таблицы в README.md и документации обновляются командой
  ``python -m app.plans_docs`` (из папки backend; ``--check`` только проверяет);
* тесты берут ожидаемые значения отсюда, их править не нужно.

Как это работает с правками из админ-панели:
поле в базе обновляется, только если его значение всё ещё равно прежнему значению из кода.
Если вы или администратор поменяли поле вручную в админ-панели, правка сохраняется.
Чтобы принудительно перезаписать ВСЕ тарифы значениями из кода, один раз запустите сервис
с переменной окружения PLANS_FORCE_SYNC=true (потом её уберите).

``None`` в числовом поле означает «без ограничений».
"""

# Общий суточный потолок запросов к ключу платформы (переопределяется переменной AI_DAILY_CAP
# или значением в админ-панели).
AI_DAILY_CAP = 2500

# Скидка при оплате за год (годовая цена = 12 месяцев минус скидка), в процентах.
YEAR_DISCOUNT_PERCENT = 20

# Тарифы в порядке показа. Цены в рублях за месяц.
#   max_ai_workflows        воркфлоу, где есть LLM- или Agent-нода
#   max_regular_workflows   остальные воркфлоу
#   ai_runs_month           запуски AI-воркфлоу в месяц
#   regular_runs_month      запуски обычных воркфлоу в месяц
#   telegram_triggers       одновременно включённых Telegram-триггеров
#   history_days            сколько дней хранится история выполнений
#   ai_chat_messages_month  сообщений AI-чата в месяц
#   extra_features          дополнительные строки в карточке тарифа (не числа)
PLANS = {
    "free": dict(
        name="Бесплатно", description="Чтобы попробовать сервис",
        price_month_rub=0,
        max_ai_workflows=5, max_regular_workflows=10,
        ai_runs_month=50, regular_runs_month=100,
        telegram_triggers=1, history_days=14,
        ai_chat_messages_month=25,
        extra_features=[],
    ),
    "pro": dict(
        name="Про", description="Для малого бизнеса и фрилансеров",
        price_month_rub=990,
        max_ai_workflows=15, max_regular_workflows=100,
        ai_runs_month=1000, regular_runs_month=3000,
        telegram_triggers=3, history_days=60,
        ai_chat_messages_month=150,
        extra_features=["Свои API-ключи (OpenAI, Groq, HF и др.)"],
    ),
    "business": dict(
        name="Бизнес", description="Для среднего и крупного бизнеса",
        price_month_rub=2990,
        max_ai_workflows=30, max_regular_workflows=None,
        ai_runs_month=3000, regular_runs_month=10000,
        telegram_triggers=10, history_days=180,
        ai_chat_messages_month=500,
        extra_features=["Свои API-ключи (OpenAI, Groq, HF и др.)", "Приоритетная поддержка"],
    ),
}

# Служебный тариф локальной версии: без ограничений, в облаке не показывается.
LOCAL_PLAN = dict(code="local", name="Локальный", description="Self-hosted: без ограничений",
                  price_month=0, price_year=0, sort_order=99, is_public=False, features=[])

LIMIT_FIELDS = ("max_ai_workflows", "max_regular_workflows", "ai_runs_month", "regular_runs_month",
                "telegram_triggers", "history_days", "ai_chat_messages_month")


# ---------------------------------------------------------------- вспомогательные функции

def fmt_num(n: int) -> str:
    """12345 -> '12 345'."""
    return f"{n:,}".replace(",", " ")


def plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(n)
    if 11 <= n % 100 <= 14:
        return many
    last = n % 10
    return one if last == 1 else few if 2 <= last <= 4 else many


def year_price_rub(month_rub: int) -> int:
    return month_rub * 12 * (100 - YEAR_DISCOUNT_PERCENT) // 100


def build_features(spec: dict) -> list[str]:
    """Строки для карточки тарифа, собранные из чисел лимитов (None = без ограничений)."""
    ai_wf, reg_wf = spec["max_ai_workflows"], spec["max_regular_workflows"]
    if ai_wf is not None and reg_wf is not None:
        first = f"{ai_wf} ИИ-сценариев и {reg_wf} обычных"
    elif ai_wf is not None:
        first = f"{ai_wf} ИИ-сценариев, обычные без ограничений"
    elif reg_wf is not None:
        first = f"ИИ-сценарии без ограничений, {reg_wf} обычных"
    else:
        first = "Сценарии без ограничений"
    items = [first]
    ai_runs, reg_runs = spec["ai_runs_month"], spec["regular_runs_month"]
    items.append(f"{fmt_num(ai_runs)} ИИ-запусков в месяц" if ai_runs is not None else "ИИ-запуски без ограничений")
    items.append(f"{fmt_num(reg_runs)} обычных запусков" if reg_runs is not None else "Обычные запуски без ограничений")
    chat = spec["ai_chat_messages_month"]
    if chat is None:
        items.append("Сообщения ИИ-помощника без ограничений")
    elif chat > 0:
        items.append(f"{fmt_num(chat)} {plural(chat, 'сообщение', 'сообщения', 'сообщений')} ИИ-помощника")
    tg = spec["telegram_triggers"]
    if tg is None:
        items.append("Telegram-триггеры без ограничений")
    elif tg > 0:
        items.append(f"{tg} Telegram-{plural(tg, 'триггер', 'триггера', 'триггеров')}")
    items.extend(spec.get("extra_features", []))
    days = spec["history_days"]
    items.append(f"История выполнений за {days} {plural(days, 'день', 'дня', 'дней')}" if days is not None
                 else "История выполнений без ограничений")
    return items


def plan_rows() -> list[dict]:
    """Тарифы в виде полей таблицы plans (цены в копейках)."""
    rows = []
    for order, (code, spec) in enumerate(PLANS.items()):
        month = spec["price_month_rub"]
        row = dict(code=code, name=spec["name"], description=spec["description"],
                   price_month=month * 100, price_year=year_price_rub(month) * 100,
                   sort_order=order, is_public=True, features=build_features(spec))
        row.update({f: spec[f] for f in LIMIT_FIELDS})
        rows.append(row)
    rows.append(dict(LOCAL_PLAN))
    return rows

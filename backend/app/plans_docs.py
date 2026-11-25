"""Обновляет таблицы тарифов в README.md и документации по значениям из plans_config.py.

    python -m app.plans_docs          # переписать таблицы
    python -m app.plans_docs --check  # только проверить (код возврата 1, если таблицы устарели)

В тексте участки помечаются парой комментариев ``<!-- plans:имя -->`` … ``<!-- /plans:имя -->``;
всё между ними генерируется и руками не правится.
"""
import re
import sys
from pathlib import Path

from .plans_config import AI_DAILY_CAP, PLANS, YEAR_DISCOUNT_PERCENT, fmt_num, plural, year_price_rub

ROOT = Path(__file__).resolve().parents[2]
TARGETS = ("README.md", "docs/guide/plans.md", "docs/admin/configuration.md")
MARKER = re.compile(r"(<!-- plans:(\w+) -->)(.*?)(<!-- /plans:\2 -->)", re.S)


def _num(v, suffix: str = "") -> str:
    return "без лимита" if v is None else f"{fmt_num(v)}{suffix}"


def _days(v) -> str:
    return "без ограничений" if v is None else f"{v} {plural(v, 'день', 'дня', 'дней')}"


def _table(rows: list[tuple[str, list[str]]]) -> str:
    names = [p["name"] for p in PLANS.values()]
    lines = ["| | " + " | ".join(names) + " |", "|---" * (len(names) + 1) + "|"]
    lines += [f"| {label} | " + " | ".join(cells) + " |" for label, cells in rows]
    return "\n".join(lines)


def _each(fn) -> list[str]:
    return [fn(p) for p in PLANS.values()]


def _price(p) -> str:
    return f"{fmt_num(p['price_month_rub'])} ₽"


def _limits_rows(labels: dict) -> list[tuple[str, list[str]]]:
    return [
        (labels["ai_wf"], _each(lambda p: _num(p["max_ai_workflows"]))),
        (labels["reg_wf"], _each(lambda p: _num(p["max_regular_workflows"]))),
        (labels["ai_runs"], _each(lambda p: _num(p["ai_runs_month"]))),
        (labels["reg_runs"], _each(lambda p: _num(p["regular_runs_month"]))),
        (labels["tg"], _each(lambda p: _num(p["telegram_triggers"]))),
        (labels["chat"], _each(lambda p: _num(p["ai_chat_messages_month"]))),
        (labels["history"], _each(lambda p: _days(p["history_days"]))),
    ]


def render_readme() -> str:
    def year(p):
        y = year_price_rub(p["price_month_rub"])
        return f"{fmt_num(y)} ₽" + (f" ({fmt_num(round(y / 12))} ₽/мес)" if y else "")
    rows = [("Цена в месяц", _each(_price)),
            (f"Цена при оплате за год (−{YEAR_DISCOUNT_PERCENT}%)", _each(year))]
    rows += _limits_rows(dict(ai_wf="AI-воркфлоу", reg_wf="Обычные воркфлоу (без AI)", ai_runs="AI-запусков в месяц",
                              reg_runs="Обычных запусков в месяц", tg="Активных Telegram-триггеров",
                              chat="Сообщений AI-чата в месяц", history="История выполнений"))
    return _table(rows)


def render_guide() -> str:
    rows = [("Цена в месяц", _each(_price)),
            ("Цена при оплате за год", _each(lambda p: f"{fmt_num(year_price_rub(p['price_month_rub']))} ₽"))]
    rows += _limits_rows(dict(ai_wf="Сценарии с нейросетью", reg_wf="Обычные сценарии",
                              ai_runs="Запусков с нейросетью в месяц", reg_runs="Обычных запусков в месяц",
                              tg="Telegram-сценариев одновременно", chat="Сообщений ИИ-помощнику в месяц",
                              history="Хранение истории запусков"))
    return _table(rows)


RENDERERS = {
    "readme": lambda: "\n" + render_readme() + "\n",
    "guide": lambda: "\n" + render_guide() + "\n",
    "cap": lambda: f"`{AI_DAILY_CAP}`",
    "discount": lambda: str(YEAR_DISCOUNT_PERCENT),
}


def render_text(text: str) -> str:
    def repl(m: re.Match) -> str:
        name = m.group(2)
        if name not in RENDERERS:
            raise SystemExit(f"Неизвестный блок plans:{name}")
        return m.group(1) + RENDERERS[name]() + m.group(4)
    return MARKER.sub(repl, text)


def main(argv: list[str]) -> int:
    check = "--check" in argv
    stale = []
    for rel in TARGETS:
        path = ROOT / rel
        if not path.exists():
            print(f"пропущен (нет файла): {rel}")
            continue
        old = path.read_text(encoding="utf-8")
        new = render_text(old)
        if new != old:
            stale.append(rel)
            if not check:
                path.write_text(new, encoding="utf-8")
    if stale:
        print(("Устарели: " if check else "Обновлены: ") + ", ".join(stale))
        return 1 if check else 0
    print("Документация уже соответствует plans_config.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

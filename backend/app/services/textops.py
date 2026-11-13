"""Преобразования текста для ноды «Обработка текста»: поиск контактов и номеров, очистка. Без нейросети — быстро и предсказуемо."""
import re

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
INTL_PHONE_RE = re.compile(r"\+\d[\d\s\-()]{8,16}\d")
RU_PHONE_RE = re.compile(r"(?<!\d)(?:\+7|8|7)?[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)")
DATE_RE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4}|\d{2})\b|\b(\d{4})-(\d{2})-(\d{2})\b")
URL_RE = re.compile(r"https?://[^\s<>\"')]+")
AMOUNT_RE = re.compile(r"(\d[\d\s]*(?:[.,]\d{1,2})?)\s*(?:₽|руб(?:\.|лей|ля|)?|р\.|rub|usd|\$|€|eur)", re.IGNORECASE)
ORDER_AFTER_WORD_RE = re.compile(
    r"(?:заказ[а-яё]*|order|№|#)\s*(?:№|#|номер|number|no\.?|n)?\s*[:\-]?\s*([A-Za-zА-Яа-я]{0,4}-?\d{2,12})",
    re.IGNORECASE,
)
BARE_NUMBER_RE = re.compile(r"(?<![\d.,/-])(\d{4,12})(?!\d|[.,]\d|[/-]\d)")
SIGNATURE_RE = re.compile(r"^\s*(--\s*$|с уважением|best regards|kind regards|sent from my|отправлено с)", re.IGNORECASE)
QUOTE_HEADER_RE = re.compile(r"^\s*(on .+ wrote:|\d{1,2}[./]\d{1,2}[./]\d{2,4}.+(написал|писал)|-{2,}\s*(original message|пересылаемое сообщение))", re.IGNORECASE)

OPERATIONS = {
    "extract_email": "Найти email",
    "extract_phone": "Найти телефон",
    "extract_order": "Найти номер заказа",
    "extract_date": "Найти дату",
    "extract_amount": "Найти сумму",
    "extract_url": "Найти ссылку",
    "extract_regex": "Найти по шаблону (регулярное выражение)",
    "normalize": "Привести к простому виду (для условий)",
    "clean_email": "Очистить письмо (убрать цитаты и подпись)",
    "first_line": "Первая строка",
    "truncate": "Обрезать до N символов",
    "lower": "Строчные буквы",
    "upper": "ЗАГЛАВНЫЕ буквы",
    "trim": "Убрать лишние пробелы",
}


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if raw.strip().startswith("+") and 10 <= len(digits) <= 15:
        return "+" + digits
    if len(digits) == 11 and digits[0] in "78":
        return "+7" + digits[1:]
    if len(digits) == 10:
        return "+7" + digits
    return raw.strip()


def _date_span(text: str) -> list[tuple[int, int]]:
    return [m.span() for m in DATE_RE.finditer(text)]


def find_order_number(text: str) -> str:
    """Номер после слов «заказ», «№», «#», «order»; иначе первое «голое» число из 4–12 цифр вне дат и телефонов."""
    for m in ORDER_AFTER_WORD_RE.finditer(text):
        value = m.group(1)
        if re.search(r"\d", value):
            return value.strip("-")
    masked = text
    for pattern in (EMAIL_RE, INTL_PHONE_RE, RU_PHONE_RE, DATE_RE):
        masked = pattern.sub(" ", masked)
    m = BARE_NUMBER_RE.search(masked)
    return m.group(1) if m else ""


def find_date(text: str) -> str:
    """Возвращает дату в формате ДД.ММ.ГГГГ."""
    m = DATE_RE.search(text)
    if not m:
        return ""
    if m.group(1):
        day, month, year = m.group(1), m.group(2), m.group(3)
        if len(year) == 2:
            year = "20" + year
    else:
        year, month, day = m.group(4), m.group(5), m.group(6)
    return f"{int(day):02d}.{int(month):02d}.{year}"


def find_amount(text: str) -> str:
    m = AMOUNT_RE.search(text)
    if not m:
        return ""
    return re.sub(r"\s", "", m.group(1)).replace(",", ".")


def clean_email_text(text: str) -> str:
    """Убирает цитируемые ответы (строки с «>»), заголовки пересылки и подпись — остаётся только суть письма."""
    lines = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.lstrip().startswith(">"):
            continue
        if QUOTE_HEADER_RE.match(line) or SIGNATURE_RE.match(line):
            break
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def apply_operation(operation: str, text: str, pattern: str = "", max_chars: int = 500) -> str:
    text = text if isinstance(text, str) else str(text)
    if operation == "extract_email":
        m = EMAIL_RE.search(text)
        return m.group(0) if m else ""
    if operation == "extract_phone":
        m = INTL_PHONE_RE.search(text) or RU_PHONE_RE.search(text)
        return normalize_phone(m.group(0)) if m else ""
    if operation == "extract_order":
        return find_order_number(text)
    if operation == "extract_date":
        return find_date(text)
    if operation == "extract_amount":
        return find_amount(text)
    if operation == "extract_url":
        m = URL_RE.search(text)
        return m.group(0).rstrip(".,;") if m else ""
    if operation == "extract_regex":
        if not pattern:
            return ""
        try:
            m = re.search(pattern, text[:20000])
        except re.error:
            return "Text Error: некорректный шаблон поиска"
        if not m:
            return ""
        return m.group(1) if m.groups() else m.group(0)
    if operation == "normalize":
        return re.sub(r"[^\w\s]", "", text.casefold()).strip()
    if operation == "clean_email":
        return clean_email_text(text)
    if operation == "first_line":
        return next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    if operation == "truncate":
        return text[:max(1, int(max_chars))]
    if operation == "lower":
        return text.lower()
    if operation == "upper":
        return text.upper()
    if operation == "trim":
        return re.sub(r"[ \t]+", " ", text).strip()
    return f"Text Error: неизвестное действие «{operation}»"

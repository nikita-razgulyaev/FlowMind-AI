/** Действия шага «Обработка текста» (совпадают с backend/app/services/textops.py). */
export interface TextOperation {
    id: string;
    label: string;
    hint: string;
    group: "Поиск" | "Очистка";
    needsPattern?: boolean;
    needsLength?: boolean;
}

export const TEXT_OPERATIONS: TextOperation[] = [
    { id: "extract_order", label: "Найти номер заказа", group: "Поиск", hint: "Находит номер после слов «заказ», «№», «#» или первое число из 4–12 цифр. Пример: «Где мой заказ? Номер 1234» → 1234." },
    { id: "extract_phone", label: "Найти телефон", group: "Поиск", hint: "Находит номер телефона и приводит его к виду +79001112233." },
    { id: "extract_email", label: "Найти email", group: "Поиск", hint: "Находит первый адрес электронной почты в тексте." },
    { id: "extract_date", label: "Найти дату", group: "Поиск", hint: "Находит дату и приводит её к виду ДД.ММ.ГГГГ. Пример: «от 05.11.26» → 05.11.2026." },
    { id: "extract_amount", label: "Найти сумму", group: "Поиск", hint: "Находит сумму рядом со словами «руб.», «₽», «$», «€». Пример: «12 500 руб» → 12500." },
    { id: "extract_url", label: "Найти ссылку", group: "Поиск", hint: "Находит первую ссылку, начинающуюся с http:// или https://." },
    { id: "extract_regex", label: "Найти по своему шаблону", group: "Поиск", needsPattern: true, hint: "Для опытных: ищет текст по регулярному выражению. Если в шаблоне есть скобки, вернётся то, что внутри первых скобок." },
    { id: "clean_email", label: "Очистить письмо", group: "Очистка", hint: "Убирает из письма цитаты предыдущей переписки и подпись, оставляет суть." },
    { id: "normalize", label: "Привести к простому виду", group: "Очистка", hint: "Строчные буквы без знаков препинания: «Support.» → «support». Удобно перед выбором варианта." },
    { id: "first_line", label: "Первая строка", group: "Очистка", hint: "Берёт только первую непустую строку." },
    { id: "truncate", label: "Обрезать до N символов", group: "Очистка", needsLength: true, hint: "Оставляет только начало текста заданной длины." },
    { id: "trim", label: "Убрать лишние пробелы", group: "Очистка", hint: "Убирает пробелы по краям и повторяющиеся пробелы внутри строки." },
    { id: "lower", label: "Строчные буквы", group: "Очистка", hint: "Переводит весь текст в строчные буквы." },
    { id: "upper", label: "ЗАГЛАВНЫЕ буквы", group: "Очистка", hint: "Переводит весь текст в заглавные буквы." },
];

export const OPERATIONS = Object.fromEntries(TEXT_OPERATIONS.map((o) => [o.id, o]));

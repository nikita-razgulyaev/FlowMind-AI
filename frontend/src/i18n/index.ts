import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import ru from "./ru.json";

// Чтобы добавить английский: создайте ./en.json с теми же ключами и добавьте его в resources.
// Выбор языка — по полю language из настроек пользователя или по языку браузера.
void i18n.use(initReactI18next).init({
    resources: { ru: { translation: ru } },
    lng: "ru",
    fallbackLng: "ru",
    interpolation: { escapeValue: false },
});

export default i18n;

const rubFormat = new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB", maximumFractionDigits: 0 });
const rubFormatCents = new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB", minimumFractionDigits: 2 });

/** Цены хранятся в копейках. */
export function formatRub(kopecks: number): string {
    return kopecks % 100 === 0 ? rubFormat.format(kopecks / 100) : rubFormatCents.format(kopecks / 100);
}

export function formatDate(value: string | null | undefined): string {
    if (!value) return "—";
    return new Date(value).toLocaleDateString(i18n.language, { day: "numeric", month: "long", year: "numeric" });
}

export function formatDateTime(value: string | null | undefined): string {
    if (!value) return "—";
    return new Date(value).toLocaleString(i18n.language, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

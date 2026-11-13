const KEY = "flowmind.tour.v1";

/** Видел ли пользователь приветствие с предложением пройти обучение. */
export function tourSeen(): boolean {
    try {
        return localStorage.getItem(KEY) === "1";
    } catch {
        return true; // хранилище недоступно — не навязываем обучение при каждом открытии
    }
}

export function markTourSeen(): void {
    try {
        localStorage.setItem(KEY, "1");
    } catch {
        /* хранилище недоступно — ничего страшного */
    }
}

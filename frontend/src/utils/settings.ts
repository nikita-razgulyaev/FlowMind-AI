import { api } from "../api/client";

export interface AppSettings {
    defaultMode: "local" | "cloud";
    defaultLocalModel: string;
    defaultCloudModel: string;
    defaultTemperature: number;
}

const KEY = "flowmind_settings";

// Значения по умолчанию зависят от режима развёртывания (задаются при старте приложения из /api/config).
let defaults: AppSettings = {
    defaultMode: "local",
    defaultLocalModel: "qwen2.5",
    defaultCloudModel: "",
    defaultTemperature: 0.3,
};

export function setDeploymentDefaults(partial: Partial<AppSettings>): void {
    defaults = { ...defaults, ...partial };
}

export function getSettings(): AppSettings {
    try {
        const raw = localStorage.getItem(KEY);
        if (!raw) return defaults;
        return { ...defaults, ...JSON.parse(raw) };
    } catch {
        return defaults;
    }
}

/** Сохраняет настройки локально (кэш) и на сервере (личные настройки пользователя). */
export function saveSettings(settings: AppSettings): void {
    localStorage.setItem(KEY, JSON.stringify(settings));
    void api.saveUserSettings(settings);
}

/** Серверные настройки — источник истины: перезаписывают локальный кэш (в т.ч. при смене аккаунта). */
export function applyServerSettings(settings: Record<string, any>): void {
    if (Object.keys(settings).length === 0) localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, JSON.stringify(settings));
}

export function clearSettingsCache(): void {
    localStorage.removeItem(KEY);
}

export function getDefaultSettings(): AppSettings {
    return defaults;
}

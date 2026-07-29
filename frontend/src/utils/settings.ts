export interface AppSettings {
    defaultMode: "local" | "cloud";
    defaultLocalModel: string;
    defaultCloudModel: string;
    defaultTemperature: number;
}

const KEY = "flowmind_settings";

export const DEFAULT_SETTINGS: AppSettings = {
    defaultMode: "local",
    defaultLocalModel: "qwen2.5",
    defaultCloudModel: "Qwen/Qwen2.5-1.5B-Instruct",
    defaultTemperature: 0.3,
};

export function getSettings(): AppSettings {
    try {
        const raw = localStorage.getItem(KEY);
        if (!raw) return DEFAULT_SETTINGS;
        return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
    } catch {
        return DEFAULT_SETTINGS;
    }
}

export function saveSettings(settings: AppSettings): void {
    localStorage.setItem(KEY, JSON.stringify(settings));
}

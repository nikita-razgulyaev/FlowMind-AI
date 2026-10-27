import { create } from "zustand";
import { api, refreshSession, setAccessToken, setSessionLostHandler } from "../api/client";
import type { AppConfig, MeResponse } from "../types/app";
import { applyServerSettings, clearSettingsCache, setDeploymentDefaults } from "../utils/settings";

interface AuthState {
    ready: boolean;
    config: AppConfig | null;
    me: MeResponse | null;
    bootstrap: () => Promise<void>;
    loadMe: () => Promise<void>;
    startSession: (accessToken: string) => Promise<void>;
    logout: () => Promise<void>;
}

export const useAuth = create<AuthState>((set, get) => ({
    ready: false,
    config: null,
    me: null,

    // Вызывается один раз при старте приложения: узнаём режим развёртывания и восстанавливаем сессию.
    bootstrap: async () => {
        const { data: config } = await api.getConfig();
        if (!config) {
            set({ ready: true });
            return;
        }
        set({ config });
        setDeploymentDefaults({ defaultMode: config.default_llm_mode, defaultLocalModel: config.ollama_model });
        if (!config.auth_required || (await refreshSession())) await get().loadMe();
        set({ ready: true });
    },

    loadMe: async () => {
        const { data } = await api.getMe();
        if (!data) {
            set({ me: null });
            return;
        }
        set({ me: data });
        const { data: settings } = await api.getUserSettings();
        if (settings) applyServerSettings(settings);
    },

    startSession: async (accessToken) => {
        setAccessToken(accessToken);
        await get().loadMe();
    },

    logout: async () => {
        await api.logout();
        setAccessToken(null);
        clearSettingsCache();
        set({ me: null });
    },
}));

setSessionLostHandler(() => useAuth.setState({ me: null }));

export const isAdmin = (s: AuthState) => s.me?.user.role === "admin";

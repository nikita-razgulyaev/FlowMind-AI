import { useState } from "react";
import { Check } from "lucide-react";
import EditorSidebar from "../components/canvas/EditorSidebar";
import { useAuth } from "../store/auth";
import {
    getDefaultSettings,
    getSettings,
    saveSettings,
    type AppSettings,
} from "../utils/settings";

const label = "block text-sm font-medium text-gray-700 mb-1.5";
const input =
    "w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500";

export default function Settings() {
    const [settings, setSettings] = useState<AppSettings>(getSettings());
    const [saved, setSaved] = useState(false);
    const isCloud = useAuth((st) => st.config?.deployment_mode === "cloud");
    const modes = (isCloud ? ["cloud"] : ["local", "cloud"]) as ("local" | "cloud")[];

    const set = (patch: Partial<AppSettings>) => {
        setSettings((s) => ({ ...s, ...patch }));
        setSaved(false);
    };

    const handleSave = () => {
        saveSettings(settings);
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
    };

    const handleReset = () => {
        setSettings(getDefaultSettings());
        saveSettings(getDefaultSettings());
    };

    return (
        <div className="flex h-screen">
            <EditorSidebar />
            <div className="flex-1 overflow-y-auto bg-gray-50">
                <div className="max-w-xl mx-auto px-8 py-10">
                    <h1 className="text-2xl font-bold text-gray-900">
                        Настройки
                    </h1>
                    <p className="text-sm text-gray-500 mt-1 mb-6">
                        Дефолты, которые подставляются при добавлении новых
                        LLM/Agent-нод на canvas.
                    </p>

                    <div className="bg-blue-50 border border-blue-200 text-blue-800 text-xs rounded-lg px-4 py-3 mb-6">
                        {isCloud ? (
                            <>Настройки сохраняются в вашем аккаунте и действуют на всех устройствах. В облачной версии доступны облачные модели.</>
                        ) : (
                            <>
                                Это дефолты для новых нод. Адрес Ollama (<code>OLLAMA_URL</code>) и ключ AI платформы
                                (<code>PLATFORM_LLM_API_KEY</code>) задаются в <code>.env</code> на сервере.
                            </>
                        )}
                    </div>

                    <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-5">
                        <div>
                            <label className={label}>Режим по умолчанию</label>
                            <div className="flex gap-2">
                                {modes.map((m) => (
                                    <button
                                        key={m}
                                        onClick={() => set({ defaultMode: m })}
                                        className={`flex-1 py-2 rounded-lg text-sm font-medium ${
                                            settings.defaultMode === m
                                                ? "bg-blue-600 text-white"
                                                : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                                        }`}
                                    >
                                        {m === "local"
                                            ? "Local (Ollama)"
                                            : "Cloud"}
                                    </button>
                                ))}
                            </div>
                        </div>

                        <div>
                            <label className={label}>
                                Локальная модель по умолчанию
                            </label>
                            <input
                                value={settings.defaultLocalModel}
                                onChange={(e) =>
                                    set({ defaultLocalModel: e.target.value })
                                }
                                placeholder="qwen2.5"
                                className={input}
                            />
                        </div>

                        <div>
                            <label className={label}>
                                Облачная модель по умолчанию
                            </label>
                            <input
                                value={settings.defaultCloudModel}
                                onChange={(e) =>
                                    set({ defaultCloudModel: e.target.value })
                                }
                                placeholder="пусто — модель по умолчанию"
                                className={input}
                            />
                        </div>

                        <div>
                            <label className={label}>
                                Temperature по умолчанию:{" "}
                                {settings.defaultTemperature}
                            </label>
                            <input
                                type="range"
                                min={0}
                                max={1}
                                step={0.1}
                                value={settings.defaultTemperature}
                                onChange={(e) =>
                                    set({
                                        defaultTemperature: parseFloat(
                                            e.target.value,
                                        ),
                                    })
                                }
                                className="w-full"
                            />
                        </div>
                    </div>

                    <div className="flex items-center gap-3 mt-5">
                        <button
                            onClick={handleSave}
                            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
                        >
                            {saved ? <Check className="w-4 h-4" /> : null}
                            {saved ? "Сохранено" : "Сохранить"}
                        </button>
                        <button
                            onClick={handleReset}
                            className="px-4 py-2 text-gray-500 hover:bg-gray-100 rounded-lg text-sm font-medium"
                        >
                            Сбросить к дефолтам
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

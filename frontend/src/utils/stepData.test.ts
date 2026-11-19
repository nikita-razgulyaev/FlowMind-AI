import { describe, expect, it } from "vitest";
import type { WorkflowEdge, WorkflowNode } from "../types/workflow";
import { buildDataGroups, buildNames, defaultRefToken, fieldToken, fieldsForStep, humanizeText, resolveRefSelection, splitRefs, upstreamIds } from "./stepData";
import { validateWorkflow } from "./validateWorkflow";

const node = (id: string, type: WorkflowNode["type"], config: Record<string, any> = {}): WorkflowNode => ({ id, type, config });
const edge = (from: string, to: string, extra: Partial<WorkflowEdge> = {}): WorkflowEdge => ({ id: `${from}-${to}`, from_node: from, to_node: to, type: "next", ...extra });

const nodes = [node("manual_1", "manual"), node("http1", "http", { url: "https://x" }), node("llm_2", "llm", { prompt: "Курс {http1.json.rates.RUB}" })];
const edges = [edge("manual_1", "http1"), edge("http1", "llm_2")];

describe("данные шагов", () => {
    it("поля HTTP-шага дополняются реальным ответом из прошлого запуска", () => {
        const fields = fieldsForStep(nodes[1], { status_code: 200, json: { rates: { RUB: 91.5 } } });
        expect(fields.map((f) => f.path)).toContain(".json.rates.RUB");
        expect(fields.find((f) => f.path === ".json.rates.RUB")?.sample).toBe("91.5");
    });

    it("понятные подписи вместо id", () => {
        const names = buildNames(nodes);
        expect(names.http1).toBe("Запрос к сервису");
        expect(humanizeText("Курс {http1.json.rates.RUB}", names)).toBe("Курс [Запрос к сервису → json → rates → RUB]");
        expect(splitRefs("{nope}", names)[0].broken).toBe(true);
    });

    it("в списке только соединённые шаги, предыдущий первым", () => {
        expect(upstreamIds("llm_2", edges)).toEqual(["http1", "manual_1"]);
        const groups = buildDataGroups("llm_2", nodes, edges, {});
        expect(groups.map((g) => g.id)).toEqual(["http1", "manual_1"]);
        expect(groups[1].trigger).toBe(true);
        // несоединённые шаги в список не попадают
        const withLoose = buildDataGroups("llm_2", [...nodes, node("text_9", "text_input")], edges, {});
        expect(withLoose.find((g) => g.id === "text_9")).toBeUndefined();
        expect(buildDataGroups("manual_1", nodes, edges, {})).toEqual([]);
    });

    it("ссылка по умолчанию — на предыдущий шаг; после запуска — {input}", () => {
        expect(defaultRefToken("llm_2", nodes, edges)).toBe("{http1.json}");
        expect(defaultRefToken("http1", nodes, edges)).toBe("{input}");
        expect(defaultRefToken("http1", nodes, [])).toBeNull();
    });
});

describe("выбор шага в списке", () => {
    const groups = buildDataGroups("llm_2", nodes, edges, {});

    it("определяет выбранный шаг и поле по значению", () => {
        expect(resolveRefSelection("{http1.json.rates.RUB}", "step", groups)).toEqual({ kind: "step", groupId: "http1", path: ".json.rates.RUB" });
        expect(resolveRefSelection("{input}", undefined, groups)).toEqual({ kind: "step", groupId: "manual_1", path: "input" });
        expect(fieldToken(groups[1], groups[1].fields[0])).toBe("{input}");
    });

    it("ручной ввод остаётся ручным, а несовпадающее значение — тоже", () => {
        expect(resolveRefSelection("{input}", "manual", groups).kind).toBe("manual");
        expect(resolveRefSelection("текст и {input}", undefined, groups).kind).toBe("manual");
    });

    it("в режиме авто берётся предыдущий шаг, а без соединений — «нет соединённых шагов»", () => {
        expect(resolveRefSelection("{input}", "auto", groups)).toEqual({ kind: "step", groupId: "http1", path: ".json" });
        expect(resolveRefSelection("{input}", "auto", []).kind).toBe("none");
    });
});

describe("проверка сценария", () => {
    it("находит ссылку на несуществующий шаг и пустые обязательные поля", () => {
        const broken = [node("manual_1", "manual"), node("llm_1", "llm", { prompt: "Ответ {http_9.json}" }), node("tg", "telegram_send", {})];
        const issues = validateWorkflow(broken, [edge("manual_1", "llm_1")]);
        expect(issues.some((i) => i.nodeId === "llm_1" && i.message.includes("несуществующий"))).toBe(true);
        expect(issues.some((i) => i.nodeId === "tg" && i.message.includes("Не заполнено"))).toBe(true);
        expect(issues.some((i) => i.nodeId === "tg" && i.message.includes("не соединён"))).toBe(true);
    });

    it("корректный сценарий без проблем", () => {
        expect(validateWorkflow(nodes, edges)).toEqual([]);
    });
});

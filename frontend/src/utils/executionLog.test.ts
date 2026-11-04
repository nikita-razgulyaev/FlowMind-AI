import { describe, expect, it } from "vitest";
import { splitBold } from "./executionLog";

describe("splitBold", () => {
    it("убирает звёздочки и помечает жирные куски", () => {
        expect(splitBold("**Саммари встречи:** релиз в среду. **Action items:**")).toEqual([
            { text: "Саммари встречи:", bold: true },
            { text: " релиз в среду. ", bold: false },
            { text: "Action items:", bold: true },
        ]);
    });

    it("оставляет текст без пары и пустые ** как есть", () => {
        expect(splitBold("2 ** 3 и **без пары")).toEqual([{ text: "2 ** 3 и **без пары", bold: false }]);
        expect(splitBold("")).toEqual([]);
    });
});

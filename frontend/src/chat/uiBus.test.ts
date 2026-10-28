import { describe, expect, it, vi } from "vitest";
import { emitUi, onUi } from "./uiBus";

describe("uiBus", () => {
  it("delivers ui events to subscribers", () => {
    const seen: string[] = [];
    onUi((detail) => seen.push(detail.name));
    emitUi({ name: "finale", payload: {} });
    expect(seen).toEqual(["finale"]);
  });

  it("stops delivering after unsubscribe", () => {
    const handler = vi.fn();
    const off = onUi(handler);
    off();
    emitUi({ name: "finale", payload: {} });
    expect(handler).not.toHaveBeenCalled();
  });
});

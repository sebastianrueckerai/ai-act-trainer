import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { emitUi } from "../chat/uiBus";
import { useEffects } from "./useEffects";

vi.mock("./confetti", () => ({ burst: vi.fn() }));
import { burst } from "./confetti";

function Harness() {
  useEffects();
  return null;
}

describe("useEffects", () => {
  it("bursts small on confetti and big on finale, nothing otherwise", () => {
    render(<Harness />);
    emitUi({ name: "confetti", payload: {} });
    emitUi({ name: "finale", payload: {} });
    emitUi({ name: "stage", payload: {} });
    expect(burst).toHaveBeenCalledWith(60);
    expect(burst).toHaveBeenCalledWith(140);
    expect(burst).toHaveBeenCalledTimes(2);
  });
});

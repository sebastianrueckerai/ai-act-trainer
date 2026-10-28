import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TolgeeProvider } from "@tolgee/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";
import { tolgee } from "../i18n";
import { ChoiceGrid, InputControl } from "./InputControl";

function withProvider(ui: ReactElement) {
  return (
    <TolgeeProvider tolgee={tolgee} fallback="…">
      {ui}
    </TolgeeProvider>
  );
}

describe("InputControl", () => {
  it("renders a text area and sends on submit", async () => {
    const onSend = vi.fn();
    render(
      withProvider(
        <InputControl
          hint={{ kind: "text", choices: [], asks: false }}
          disabled={false}
          onSend={onSend}
          onAdvance={vi.fn()}
        />,
      ),
    );
    expect(await screen.findByPlaceholderText("Schreib etwas …")).toBeInTheDocument();
    const send = await screen.findByRole("button", { name: "Senden" });
    await userEvent.type(screen.getByRole("textbox"), "Was gilt für KI-Systeme?");
    await userEvent.click(send);
    expect(onSend).toHaveBeenCalledWith("Was gilt für KI-Systeme?", undefined);
    expect(screen.getByRole("textbox")).toHaveValue("");
  });

  it("sends nothing when the text is empty", async () => {
    const onSend = vi.fn();
    render(
      withProvider(
        <InputControl
          hint={{ kind: "text", choices: [], asks: false }}
          disabled={false}
          onSend={onSend}
          onAdvance={vi.fn()}
        />,
      ),
    );
    await userEvent.click(await screen.findByRole("button", { name: "Senden" }));
    expect(onSend).not.toHaveBeenCalled();
  });

  it("offers yes and no buttons beside the reachable text area", async () => {
    const onSend = vi.fn();
    render(
      withProvider(
        <InputControl
          hint={{ kind: "yes_no", choices: [], asks: false }}
          disabled={false}
          onSend={onSend}
          onAdvance={vi.fn()}
        />,
      ),
    );
    const yes = await screen.findByRole("button", { name: "Ja" });
    const no = screen.getByRole("button", { name: "Nein" });
    expect(yes).toHaveClass("ui-button--primary");
    expect(no).toHaveClass("ui-button--primary");
    await userEvent.click(yes);
    expect(onSend).toHaveBeenCalledWith("yes", "Ja");
    await userEvent.click(no);
    expect(onSend).toHaveBeenCalledWith("no", "Nein");
    expect(no).toBeInTheDocument();
    expect(screen.getByRole("textbox")).toBeInTheDocument();
  });

  it("advances but sends nothing for a bare confirm hint", async () => {
    const onSend = vi.fn();
    const onAdvance = vi.fn();
    render(
      withProvider(
        <InputControl hint={{ kind: "confirm", asks: false }} disabled={false} onSend={onSend} onAdvance={onAdvance} />,
      ),
    );
    const confirm = await screen.findByRole("button", { name: "Bestätigen" });
    expect(confirm).toHaveClass("ui-button--primary");
    await userEvent.click(confirm);
    expect(onAdvance).toHaveBeenCalledWith();
    expect(onSend).not.toHaveBeenCalled();
  });

  it("advances but sends nothing for a confirm hint with its own label", async () => {
    const onSend = vi.fn();
    const onAdvance = vi.fn();
    render(
      withProvider(
        <InputControl
          hint={{ kind: "confirm", label: "Weiter", asks: false }}
          disabled={false}
          onSend={onSend}
          onAdvance={onAdvance}
        />,
      ),
    );
    await userEvent.click(await screen.findByRole("button", { name: "Weiter" }));
    expect(onAdvance).toHaveBeenCalledWith();
    expect(onSend).not.toHaveBeenCalled();
  });

  it.each(["Weiter zu Kapitel 2", "Zum Test"])(
    "puts the chapter end's own label on the button: %s",
    async (label) => {
      const onAdvance = vi.fn();
      render(
        withProvider(
          <InputControl
            hint={{ kind: "confirm", label, asks: false }}
            disabled={false}
            onSend={vi.fn()}
            onAdvance={onAdvance}
          />,
        ),
      );
      await userEvent.click(await screen.findByRole("button", { name: label }));
      expect(onAdvance).toHaveBeenCalledTimes(1);
      expect(screen.getByRole("textbox")).toHaveAttribute("placeholder", "Oder frag mich etwas …");
    },
  );
});

describe("ChoiceGrid", () => {
  it("sends a chip's key but shows it prefixed with its own letter", async () => {
    const onSend = vi.fn();
    render(
      withProvider(
        <ChoiceGrid
          hint={{ kind: "choices", choices: [{ key: "B", label: "Buchhaltung" }], asks: false }}
          disabled={false}
          onSend={onSend}
        />,
      ),
    );
    await userEvent.click(await screen.findByRole("button", { name: "B. Buchhaltung" }));
    expect(onSend).toHaveBeenCalledWith("B", "B. Buchhaltung");
  });

  it("falls back to a positional letter when a chip's key is not one", async () => {
    const onSend = vi.fn();
    render(
      withProvider(
        <ChoiceGrid
          hint={{
            kind: "choices",
            choices: [
              { key: "buchhaltung", label: "Buchhaltung" },
              { key: "personal", label: "Personal" },
            ],
            asks: false,
          }}
          disabled={false}
          onSend={onSend}
        />,
      ),
    );
    expect(await screen.findByRole("button", { name: "A. Buchhaltung" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "B. Personal" }));
    expect(onSend).toHaveBeenCalledWith("personal", "B. Personal");
  });
});

it("invites a question while the tutor waits for a nod", () => {
  render(
    withProvider(
      <InputControl
        hint={{ kind: "confirm", choices: [], label: "Ja, weiter", asks: false }}
        disabled={false}
        onSend={() => {}}
        onAdvance={() => {}}
      />,
    ),
  );

  expect(screen.getByRole("textbox")).toHaveAttribute("placeholder", "Oder frag mich etwas …");
});

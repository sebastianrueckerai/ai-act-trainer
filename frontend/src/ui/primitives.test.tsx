import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  Avatar,
  Badge,
  Bubble,
  Button,
  Card,
  Cells,
  Chip,
  Frame,
  Icon,
  Notice,
  TextArea,
  TextInput,
} from "./index";

describe("primitives", () => {
  it("styles a primary Button with an icon", () => {
    render(
      <Button variant="primary" icon="send">
        Senden
      </Button>,
    );
    const button = screen.getByRole("button", { name: /Senden/ });
    expect(button.className).toContain("ui-button--primary");
    expect(button.querySelector("svg[data-name='send']")).toBeInTheDocument();
  });

  it("splits a bubble's text on blank lines into paragraphs", () => {
    const { container } = render(
      <Bubble role="assistant">{"Erster Absatz.\n\nZweiter Absatz.\nGleiche Zeile."}</Bubble>,
    );
    const paragraphs = container.querySelectorAll(".ui-bubble p");
    expect(paragraphs).toHaveLength(2);
    expect(paragraphs[0]).toHaveTextContent("Erster Absatz.");
    // a single newline stays inside its paragraph, held by white-space: pre-wrap
    expect(paragraphs[1].textContent).toBe("Zweiter Absatz.\nGleiche Zeile.");
  });

  it("marks selected chips", () => {
    render(
      <>
        <Chip selected>Ja</Chip>
        <Chip>Nein</Chip>
      </>,
    );
    expect(screen.getByRole("button", { name: "Ja" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Nein" })).toHaveAttribute("aria-pressed", "false");
  });

  it("renders the file, check and lock icons", () => {
    render(
      <>
        <Icon name="file" />
        <Icon name="check" />
        <Icon name="lock" />
      </>,
    );
    expect(document.querySelectorAll("svg.ui-icon").length).toBe(3);
  });

  it("draws one cell per state, the label as the bar's value text and no flag unless asked", () => {
    const { rerender } = render(
      <Cells cells={["ok", "wrong", "ahead"]} label="1 von 3 richtig" />,
    );
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "1 von 3 richtig");
    const states = () =>
      Array.from(document.querySelectorAll(".ui-cell")).map((cell) => cell.getAttribute("data-state"));
    expect(states()).toEqual(["ok", "wrong", "ahead"]);
    expect(document.querySelector(".ui-flag")).toBeNull();
    expect(document.querySelector(".ui-cell[data-flash]")).toBeNull();

    rerender(<Cells cells={["done", "now", "ahead"]} flag="down" label="Schritt 2 von 3" />);
    expect(states()).toEqual(["done", "now", "ahead"]);
    const flag = document.querySelector("svg.ui-flag");
    expect(flag).toHaveAttribute("data-state", "down");
    expect(flag).toHaveAttribute("viewBox", "0 0 5 7");
    expect(flag).toHaveAttribute("aria-hidden", "true");

    rerender(<Cells cells={["done", "done", "done"]} flag="up" label="Schritt 3 von 3" flashIndex={2} />);
    expect(document.querySelector(".ui-flag")).toHaveAttribute("data-state", "up");
    const flashing = document.querySelectorAll(".ui-cell[data-flash]");
    expect(Array.from(flashing)).toEqual([document.querySelectorAll(".ui-cell")[2]]);
  });

  it("rests the flag at the foot of the pole and hoists it only when the bar fills", () => {
    const cloth = () => document.querySelector(".ui-flag rect + rect");
    const flag = () => document.querySelector(".ui-flag");
    const { rerender } = render(
      <Cells cells={["done", "now"]} flag="down" label="Schritt 2 von 2" />,
    );
    expect(cloth()).toHaveAttribute("y", "4");
    expect(flag()).not.toHaveClass("ui-flag--hoist");

    rerender(<Cells cells={["done", "done"]} flag="up" label="Schritt 2 von 2" />);
    expect(cloth()).toHaveAttribute("y", "0");
    expect(flag()).toHaveClass("ui-flag--hoist");

    rerender(<Cells cells={["now", "ahead"]} flag="down" label="Schritt 1 von 2" />);
    expect(cloth()).toHaveAttribute("y", "4");
    expect(flag()).not.toHaveClass("ui-flag--hoist");
  });

  it("raises no hoist for a bar that arrives full", () => {
    render(<Cells cells={["done", "done"]} flag="up" label="Schritt 2 von 2" />);
    expect(document.querySelector(".ui-flag rect + rect")).toHaveAttribute("y", "0");
    expect(document.querySelector(".ui-flag")).not.toHaveClass("ui-flag--hoist");
  });

  it("renders an avatar image when present and a fallback letter otherwise", () => {
    const { rerender } = render(
      <Avatar name="Marvin" imageUrl="/api/personas/marvin/images/happy" mood="happy" />,
    );
    expect(document.querySelector(".ui-avatar img")).toHaveAttribute(
      "src",
      "/api/personas/marvin/images/happy",
    );
    rerender(<Avatar name="Marvin" imageUrl={null} mood="neutral" />);
    expect(document.querySelector(".ui-avatar-fallback")).toHaveTextContent("M");
  });

  it("renders a notice as a status with its title, its body and an optional icon", () => {
    const { rerender } = render(
      <Notice title="Großer Andrang" icon="hourglass">
        <p>Um 14:00 Uhr geht es weiter.</p>
      </Notice>,
    );
    const notice = screen.getByRole("status");
    expect(notice.className).toContain("ui-notice");
    expect(screen.getByRole("heading", { name: "Großer Andrang" })).toBeInTheDocument();
    expect(notice).toHaveTextContent("Um 14:00 Uhr geht es weiter.");
    expect(notice.querySelector("svg[data-name='hourglass']")).toBeInTheDocument();

    rerender(<Notice title="Großer Andrang">Text</Notice>);
    expect(screen.getByRole("status").querySelector("svg")).toBeNull();
  });

  it("renders bubbles, frames, cards, badges and the text inputs", () => {
    render(
      <Frame>
        <Bubble role="user">Hallo</Bubble>
        <Bubble role="assistant">Willkommen</Bubble>
        <Card title="Musterantwort">
          <Badge tone="success">Richtig</Badge>
        </Card>
        <TextInput aria-label="Name" />
        <TextArea aria-label="Nachricht" />
      </Frame>,
    );
    expect(screen.getByText("Hallo").closest(".ui-bubble")?.className).toContain("ui-bubble--user");
    expect(screen.getByText("Willkommen").closest(".ui-bubble")?.className).toContain(
      "ui-bubble--assistant",
    );
    expect(screen.getByText("Richtig").className).toContain("ui-badge--success");
    expect(screen.getByLabelText("Name").className).toContain("ui-input");
    expect(screen.getByLabelText("Nachricht").className).toContain("ui-textarea");
  });
});

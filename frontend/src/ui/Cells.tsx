import { useState } from "react";

export type CellState = "done" | "now" | "ahead" | "ok" | "wrong";

export function Cells({
  cells,
  flag,
  label,
  flashIndex,
}: {
  cells: CellState[];
  flag?: "down" | "up";
  label: string;
  flashIndex?: number;
}) {
  // The flag rests at the foot of the pole and is hoisted when the chapter fills, never
  // when a bar mounts already full.
  const [shownFlag, setShownFlag] = useState(flag);
  const [hoist, setHoist] = useState(false);
  if (flag !== shownFlag) {
    setShownFlag(flag);
    setHoist(shownFlag === "down" && flag === "up");
  }
  return (
    <span className="ui-cells" role="progressbar" aria-valuetext={label}>
      {cells.map((state, index) => (
        <i
          key={index}
          className="ui-cell"
          data-state={state}
          data-flash={index === flashIndex || undefined}
        />
      ))}
      {flag && (
        <svg
          className={hoist ? "ui-flag ui-flag--hoist" : "ui-flag"}
          data-state={flag}
          viewBox="0 0 5 7"
          shapeRendering="crispEdges"
          aria-hidden="true"
        >
          <rect x="0" y="0" width="1" height="7" />
          <rect x="1" y={flag === "up" ? 0 : 4} width="4" height="3" />
        </svg>
      )}
    </span>
  );
}

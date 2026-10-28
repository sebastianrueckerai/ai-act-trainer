import { useEffect } from "react";
import { onUi } from "../chat/uiBus";
import { burst } from "./confetti";

export function useEffects(): void {
  useEffect(
    () =>
      onUi((detail) => {
        if (detail.name === "confetti") burst(60);
        else if (detail.name === "finale") burst(140);
      }),
    [],
  );
}

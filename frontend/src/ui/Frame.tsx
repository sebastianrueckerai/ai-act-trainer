import type { HTMLAttributes } from "react";
import { cx } from "./cx";

export function Frame({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cx("ui-frame", className)} {...rest} />;
}

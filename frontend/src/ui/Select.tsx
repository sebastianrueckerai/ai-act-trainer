import type { SelectHTMLAttributes } from "react";
import { cx } from "./cx";

export function Select({ className, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cx("ui-select", className)} {...rest} />;
}

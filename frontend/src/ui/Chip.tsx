import type { ButtonHTMLAttributes } from "react";
import { cx } from "./cx";

export function Chip({
  selected = false,
  className,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { selected?: boolean }) {
  return (
    <button
      type="button"
      className={cx("ui-chip", className)}
      data-selected={selected}
      aria-pressed={selected}
      {...rest}
    />
  );
}

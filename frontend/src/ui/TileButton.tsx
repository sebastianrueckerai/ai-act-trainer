import type { ButtonHTMLAttributes } from "react";
import { cx } from "./cx";

export function TileButton({ className, ...rest }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button type="button" className={cx("ui-tile", className)} {...rest} />;
}

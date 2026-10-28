import type { InputHTMLAttributes } from "react";
import { cx } from "./cx";

export function TextInput({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cx("ui-input", className)} {...rest} />;
}

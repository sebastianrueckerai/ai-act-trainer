import type { ButtonHTMLAttributes } from "react";
import { Icon, type IconName } from "./Icon";
import { cx } from "./cx";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
  icon?: IconName;
};

export function Button({ variant = "secondary", icon, className, children, ...rest }: ButtonProps) {
  return (
    <button type="button" className={cx("ui-button", `ui-button--${variant}`, className)} {...rest}>
      {icon && <Icon name={icon} />}
      {children}
    </button>
  );
}

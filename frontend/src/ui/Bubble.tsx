import type { HTMLAttributes, ReactNode } from "react";
import { cx } from "./cx";

export function Bubble({
  role,
  footer,
  children,
  className,
  ...rest
}: {
  role: "user" | "assistant";
  footer?: ReactNode;
  children: ReactNode;
} & HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cx("ui-bubble", `ui-bubble--${role}`, className)} {...rest}>
      {typeof children === "string"
        ? children.split(/\n[ \t]*\n/).map((paragraph, index) => <p key={index}>{paragraph}</p>)
        : children}
      {footer}
    </div>
  );
}

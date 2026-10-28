import type { HTMLAttributes, ReactNode } from "react";
import { cx } from "./cx";

export function Card({
  title,
  className,
  children,
  ...rest
}: Omit<HTMLAttributes<HTMLElement>, "title"> & { title?: ReactNode }) {
  return (
    <section className={cx("ui-card", className)} {...rest}>
      {title !== undefined && <h3 className="ui-card-title">{title}</h3>}
      {children}
    </section>
  );
}

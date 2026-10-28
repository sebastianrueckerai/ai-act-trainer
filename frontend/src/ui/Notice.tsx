import type { HTMLAttributes, ReactNode } from "react";
import { Icon, type IconName } from "./Icon";
import { cx } from "./cx";

export function Notice({
  title,
  icon,
  className,
  children,
  ...rest
}: Omit<HTMLAttributes<HTMLElement>, "title"> & { title: ReactNode; icon?: IconName }) {
  return (
    <section className={cx("ui-notice", className)} role="status" {...rest}>
      {icon && <Icon name={icon} />}
      <div className="ui-notice-body">
        <h3 className="ui-notice-title">{title}</h3>
        {children}
      </div>
    </section>
  );
}

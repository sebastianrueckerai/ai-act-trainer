import { forwardRef, type TextareaHTMLAttributes } from "react";
import { cx } from "./cx";

export const TextArea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function TextArea({ className, ...rest }, ref) {
    return <textarea ref={ref} className={cx("ui-textarea", className)} {...rest} />;
  },
);

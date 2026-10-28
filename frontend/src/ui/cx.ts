export const cx = (...parts: (string | undefined)[]) => parts.filter(Boolean).join(" ");

export type UiEventDetail = { name: string; payload: Record<string, unknown> };

const bus = new EventTarget();

export function emitUi(detail: UiEventDetail): void {
  bus.dispatchEvent(new CustomEvent<UiEventDetail>("ui", { detail }));
}

export function onUi(handler: (detail: UiEventDetail) => void): () => void {
  const listener = (event: Event) => handler((event as CustomEvent<UiEventDetail>).detail);
  bus.addEventListener("ui", listener);
  return () => bus.removeEventListener("ui", listener);
}

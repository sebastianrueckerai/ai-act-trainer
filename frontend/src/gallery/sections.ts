export const GALLERY_SECTIONS = [
  "buttons",
  "inputs",
  "chat",
  "cards",
  "icons",
  "progress",
  "avatars",
  "stage",
  "notices",
  "chapter",
] as const;

export type GallerySection = (typeof GALLERY_SECTIONS)[number];

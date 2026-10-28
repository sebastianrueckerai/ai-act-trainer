const ICONS = {
  send: [
    "........",
    ".....#..",
    "......#.",
    "#######.",
    "......#.",
    ".....#..",
    "........",
    "........",
  ],
  lock: [
    "........",
    "..##....",
    "..#.#...",
    "..#.#...",
    ".#####..",
    ".#####..",
    ".#####..",
    "........",
  ],
  check: [
    "........",
    "......##",
    ".....##.",
    "....##..",
    "#..##...",
    ".###....",
    "..#.....",
    "........",
  ],
  look: [
    "........",
    "........",
    ".#....#.",
    "#.####.#",
    ".#....#.",
    "........",
    "........",
    "........",
  ],
  mode: [
    "........",
    "..###...",
    ".#...#..",
    "#.....#.",
    "#.....#.",
    ".#...#..",
    "..###...",
    "........",
  ],
  signout: [
    "........",
    ".####..#",
    ".#..#.##",
    ".#..#..#",
    ".####..#",
    "......##",
    ".....###",
    "........",
  ],
  file: [
    "..###...",
    "..#..#..",
    "..#..#..",
    "..#..#..",
    "..#..#..",
    "..####..",
    "........",
    "........",
  ],
  text: [
    "........",
    "#######.",
    "........",
    "#####...",
    "........",
    "#######.",
    "........",
    "###.....",
  ],
  restart: [
    "........",
    "..###...",
    ".#...#..",
    "#.....##",
    "#.......",
    ".#...#..",
    "..###...",
    "........",
  ],
  down: [
    "........",
    "...##...",
    "...##...",
    "...##...",
    ".######.",
    "..####..",
    "...##...",
    "........",
  ],
  hourglass: [
    "........",
    ".######.",
    "..#..#..",
    "...##...",
    "...##...",
    "..####..",
    ".######.",
    "........",
  ],
  "flag-de": [
    "kkkkkkkk",
    "kkkkkkkk",
    "kkkkkkkk",
    "rrrrrrrr",
    "rrrrrrrr",
    "gggggggg",
    "gggggggg",
    "gggggggg",
  ],
  "flag-en": [
    "bbwrrwbb",
    "bbwrrwbb",
    "wwwrrwww",
    "rrrrrrrr",
    "rrrrrrrr",
    "wwwrrwww",
    "bbwrrwbb",
    "bbwrrwbb",
  ],
} as const;

export type IconName = keyof typeof ICONS;

// The plain icons are one shape in the current text colour ("#" over "."). A
// flag needs its own colours, so a handful of letters carry a fixed fill.
const PALETTE: Record<string, string> = {
  k: "#000",
  r: "#d00",
  g: "#ffce00",
  w: "#fff",
  b: "#00247d",
};

// 8x8 art at the screen's own pixel size: 32px on a desktop, 16px on a phone,
// which .ui-icon enforces in CSS over these attributes (D66).
export function Icon({ name, size = 32 }: { name: IconName; size?: number }) {
  return (
    <svg
      className="ui-icon"
      data-name={name}
      width={size}
      height={size}
      viewBox="0 0 8 8"
      shapeRendering="crispEdges"
      aria-hidden="true"
      focusable="false"
    >
      {ICONS[name].flatMap((row, y) =>
        row.split("").map((cell, x) => {
          if (cell === ".") return null;
          const fill = cell === "#" ? undefined : PALETTE[cell];
          return <rect key={`${x}-${y}`} x={x} y={y} width={1} height={1} fill={fill} />;
        }),
      )}
    </svg>
  );
}

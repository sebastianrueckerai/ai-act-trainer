type Particle = {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  color: string;
  life: number;
};

const COLOR_VARS = ["--c-primary", "--c-accent", "--c-success", "--c-secondary"];
const FALLBACK_COLORS = ["#38bdf8", "#fbbf24", "#16a34a", "#16233a"];
const LIFE_FRAMES = 130;
// The burst lives about LIFE_FRAMES display frames; a wall-clock wait spans it
// on any refresh rate.
const BURST_MS = Math.ceil((LIFE_FRAMES / 60) * 1000);

export function reducedMotion(): boolean {
  return (
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

// How long a burst plays, and zero when it plays nothing: whoever waits for the
// confetti to finish waits exactly as long as the confetti is worth.
export function burstMs(): number {
  return reducedMotion() ? 0 : BURST_MS;
}

function paletteColors(): string[] {
  const styles = getComputedStyle(document.documentElement);
  const colors = COLOR_VARS.map((name) => styles.getPropertyValue(name).trim()).filter(Boolean);
  return colors.length > 0 ? colors : FALLBACK_COLORS;
}

export function burst(count: number): void {
  if (reducedMotion()) return;
  const width = window.innerWidth;
  const height = window.innerHeight;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  canvas.className = "ui-confetti";
  document.body.appendChild(canvas);
  const ctx = canvas.getContext("2d");
  if (ctx === null) {
    canvas.remove();
    return;
  }
  ctx.imageSmoothingEnabled = false;
  const pixel = document.documentElement.dataset.look === "pixel";
  const colors = paletteColors();
  const particles: Particle[] = Array.from({ length: count }, () => ({
    x: Math.random() * width,
    y: -12 - Math.random() * height * 0.2,
    vx: (Math.random() - 0.5) * 2,
    vy: 2 + Math.random() * 2.5,
    size: pixel ? 12 : 8,
    color: colors[Math.floor(Math.random() * colors.length)] ?? FALLBACK_COLORS[0]!,
    life: LIFE_FRAMES,
  }));

  const frame = () => {
    ctx.clearRect(0, 0, width, height);
    let alive = 0;
    for (const particle of particles) {
      particle.life -= 1;
      particle.x += particle.vx;
      particle.y += particle.vy;
      particle.vy = Math.min(particle.vy + 0.05, 6);
      if (particle.life <= 0 || particle.y > height + 12) continue;
      alive += 1;
      ctx.fillStyle = particle.color;
      if (pixel) {
        ctx.fillRect(Math.round(particle.x), Math.round(particle.y), particle.size, particle.size);
      } else {
        ctx.beginPath();
        ctx.arc(particle.x, particle.y, particle.size / 2, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    if (alive > 0) {
      requestAnimationFrame(frame);
    } else {
      canvas.remove();
    }
  };
  requestAnimationFrame(frame);
}

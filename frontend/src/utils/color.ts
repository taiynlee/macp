const PALETTE = [200, 28, 265, 140, 340, 55]

export function agentHue(name: string): number {
  let h = 5381
  for (const c of name) h = ((h << 5) + h) ^ c.charCodeAt(0)
  return PALETTE[Math.abs(h) % PALETTE.length]
}

export function agentColors(name: string, light = false) {
  const h = agentHue(name)
  if (light) return {
    bg:     `hsl(${h},60%,95%)`,
    border: `hsl(${h},55%,75%)`,
    text:   `hsl(${h},55%,22%)`,
    accent: `hsl(${h},65%,40%)`,
    header: `hsl(${h},50%,88%)`,
  }
  return {
    bg:     `hsl(${h},55%,9%)`,
    border: `hsl(${h},55%,24%)`,
    text:   `hsl(${h},75%,80%)`,
    accent: `hsl(${h},70%,65%)`,
    header: `hsl(${h},45%,14%)`,
  }
}

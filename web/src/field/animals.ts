const TAU = Math.PI * 2;

export interface AnimalColors {
  body: string;
  ink: string;
}

/** Top-down sheep facing +x: a scalloped fleece and a dark head with two ears. */
export function drawSheepGlyph(ctx: CanvasRenderingContext2D, x: number, y: number, size: number, angle: number, colors: AnimalColors): void {
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(angle);
  ctx.fillStyle = colors.ink;
  ctx.beginPath();
  ctx.ellipse(size * 1.45, 0, size * 0.5, size * 0.36, 0, 0, TAU);
  ctx.ellipse(size * 1.2, -size * 0.5, size * 0.3, size * 0.14, 0.5, 0, TAU);
  ctx.ellipse(size * 1.2, size * 0.5, size * 0.3, size * 0.14, -0.5, 0, TAU);
  ctx.fill();
  const lobes = 9;
  const fleece = new Path2D();
  for (let i = 0; i < lobes; i++) {
    const a = (i / lobes) * TAU;
    const cx = Math.cos(a) * size * 0.72;
    const cy = Math.sin(a) * size * 0.6;
    fleece.moveTo(cx + size * 0.42, cy);
    fleece.arc(cx, cy, size * 0.42, 0, TAU);
  }
  ctx.lineWidth = size * 0.2;
  ctx.strokeStyle = colors.ink;
  ctx.stroke(fleece);
  ctx.fillStyle = colors.body;
  ctx.fill(fleece);
  ctx.beginPath();
  ctx.ellipse(0, 0, size * 0.78, size * 0.66, 0, 0, TAU);
  ctx.fill();
  ctx.restore();
}

/** Top-down wolf facing +x: long body, bushy tail, pointed muzzle and pricked ears. */
export function drawWolfGlyph(ctx: CanvasRenderingContext2D, x: number, y: number, size: number, angle: number, colors: AnimalColors): void {
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(angle);
  ctx.fillStyle = colors.body;
  ctx.strokeStyle = colors.ink;
  ctx.lineWidth = size * 0.14;
  ctx.lineJoin = "round";
  const outline = new Path2D();
  outline.moveTo(size * 1.95, 0);
  outline.lineTo(size * 1.4, -size * 0.32);
  outline.lineTo(size * 1.18, -size * 0.82);
  outline.lineTo(size * 0.98, -size * 0.38);
  outline.lineTo(size * 0.72, -size * 0.3);
  outline.quadraticCurveTo(size * 0.1, -size * 0.8, -size * 0.9, -size * 0.42);
  outline.lineTo(-size * 1.2, -size * 0.18);
  outline.quadraticCurveTo(-size * 1.8, -size * 0.55, -size * 2.1, 0);
  outline.quadraticCurveTo(-size * 1.8, size * 0.55, -size * 1.2, size * 0.18);
  outline.lineTo(-size * 0.9, size * 0.42);
  outline.quadraticCurveTo(size * 0.1, size * 0.8, size * 0.72, size * 0.3);
  outline.lineTo(size * 0.98, size * 0.38);
  outline.lineTo(size * 1.18, size * 0.82);
  outline.lineTo(size * 1.4, size * 0.32);
  outline.closePath();
  ctx.fill(outline);
  ctx.stroke(outline);
  ctx.fillStyle = colors.ink;
  ctx.beginPath();
  ctx.arc(size * 1.95, 0, size * 0.13, 0, TAU);
  ctx.fill();
  ctx.restore();
}

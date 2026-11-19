// Camera moves and timed cuts for full-frame, opaque illustration plates.
import { clamp, lerp, ss } from '../lib.js';

function positive(value, label) {
  if (!Number.isFinite(value) || value <= 0) throw new RangeError(`${label} must be positive`);
  return value;
}

function fraction(value, label) {
  if (!Number.isFinite(value) || value < 0 || value > 1) throw new RangeError(`${label} must be in [0, 1]`);
  return value;
}

function camera(pose) {
  const { x, y, zoom } = pose;
  if (!Number.isFinite(zoom) || zoom < 1) throw new RangeError('camera zoom must be at least 1');
  return { x: fraction(x, 'camera x'), y: fraction(y, 'camera y'), zoom };
}

function cropFor(shot, pose, width, height) {
  const { sourceWidth, sourceHeight, anchorX, anchorY } = shot;
  const cover = Math.max(width / sourceWidth, height / sourceHeight);
  const w = Math.min(sourceWidth, width / (cover * pose.zoom));
  const h = Math.min(sourceHeight, height / (cover * pose.zoom));
  return {
    x: clamp(pose.x * sourceWidth - anchorX * w, 0, sourceWidth - w),
    y: clamp(pose.y * sourceHeight - anchorY * h, 0, sourceHeight - h),
    w, h,
  };
}

export function createIllustratedSequence(shots) {
  if (!Array.isArray(shots) || !shots.length) throw new Error('an illustrated sequence needs at least one shot');
  let duration = 0;
  const timeline = shots.map(({ image, duration: seconds, from, to, anchor = [.5, .5], blendIn = 0 }, index) => {
    const start = duration;
    duration += positive(seconds, 'shot duration');
    if (!Number.isFinite(blendIn) || blendIn < 0 || blendIn > seconds || (index === 0 && blendIn > 0)) {
      throw new RangeError('blendIn must fit inside its incoming shot and be zero on the first shot');
    }
    const sourceWidth = positive(image?.naturalWidth ?? image?.width, 'decoded image width');
    const sourceHeight = positive(image?.naturalHeight ?? image?.height, 'decoded image height');
    const first = camera({ x: .5, y: .5, zoom: 1, ...from });
    const last = camera({ ...first, ...to });
    const [ax, ay] = anchor;
    return { image, sourceWidth, sourceHeight, start, end: duration, blendIn, first, last,
      anchorX: fraction(ax, 'screen anchor x'), anchorY: fraction(ay, 'screen anchor y') };
  });

  function paint(ctx, index, time, width, height) {
    const shot = timeline[index];
    // Keep the outgoing camera moving until the incoming dissolve has finished.
    const visibleEnd = shot.end + (timeline[index + 1]?.blendIn ?? 0);
    const progress = ss((time - shot.start) / (visibleEnd - shot.start));
    // Clamp the endpoints before interpolating, so a pan never jolts to a stop against an edge.
    const a = cropFor(shot, shot.first, width, height);
    const b = cropFor(shot, shot.last, width, height);
    ctx.drawImage(shot.image, lerp(a.x, b.x, progress), lerp(a.y, b.y, progress),
      lerp(a.w, b.w, progress), lerp(a.h, b.h, progress), 0, 0, width, height);
  }

  function draw(ctx, time, width = ctx.canvas.width, height = ctx.canvas.height) {
    if (!Number.isFinite(time)) throw new RangeError('time must be finite');
    positive(width, 'viewport width');
    positive(height, 'viewport height');
    const t = clamp(time, 0, duration);
    const index = timeline.findLastIndex(shot => shot.start <= t);
    const { start, blendIn } = timeline[index];
    ctx.save();
    try {
      ctx.globalCompositeOperation = 'source-over';
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = 'high';
      ctx.globalAlpha = 1;
      if (t < start + blendIn) {
        paint(ctx, index - 1, t, width, height);
        ctx.globalAlpha = ss((t - start) / blendIn);
      }
      paint(ctx, index, t, width, height);
    } finally {
      ctx.restore();
    }
  }

  return { duration, draw };
}

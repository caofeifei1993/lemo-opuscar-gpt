import assert from 'node:assert/strict';
import test from 'node:test';
import { createIllustratedSequence } from '../../core/render/illustrated-sequence.js';

const wide = { width: 1600, height: 900 };
const portrait = { width: 900, height: 1600 };

function sample(sequence, time, width = 640, height = 360) {
  const draws = [];
  const ctx = {
    canvas: { width, height },
    save() {}, restore() {},
    drawImage(image, ...crop) { draws.push({ image, crop, alpha: this.globalAlpha }); },
  };
  sequence.draw(ctx, time);
  return draws;
}

test('a cue-aligned dissolve moves both cameras without fading through black or extending the film', () => {
  const sequence = createIllustratedSequence([
    { image: wide, duration: 2, to: { zoom: 1.2 } },
    { image: portrait, duration: 3, blendIn: .4, to: { zoom: 1.3 } },
  ]);
  assert.equal(sequence.duration, 5);
  const cut = sample(sequence, 2);
  const midpoint = sample(sequence, 2.2);
  const [outgoing, incoming] = midpoint;
  assert.deepEqual(cut.map(draw => draw.alpha), [1, 0]);
  assert.equal(outgoing.image, wide);
  assert.equal(incoming.image, portrait);
  assert.equal(outgoing.alpha, 1);
  assert.ok(Math.abs(incoming.alpha - .5) < 1e-10);
  assert.ok(outgoing.crop[2] < cut[0].crop[2]);
  assert.ok(incoming.crop[2] < cut[1].crop[2]);
  assert.deepEqual(sample(sequence, 2.4).map(draw => draw.image), [portrait]);
  sample(sequence, 5);
  sample(sequence, 0);
  assert.deepEqual(sample(sequence, 2.2), midpoint);
});

test('a hard cut switches plates on its cue and times outside the sequence hold the endpoints', () => {
  const sequence = createIllustratedSequence([
    { image: wide, duration: 1 }, { image: portrait, duration: 2, to: { zoom: 1.2 } },
  ]);
  assert.deepEqual(sample(sequence, 1 - 1 / 24).map(draw => draw.image), [wide]);
  assert.deepEqual(sample(sequence, 1).map(draw => draw.image), [portrait]);
  assert.deepEqual(sample(sequence, -1), sample(sequence, 0));
  assert.deepEqual(sample(sequence, 4), sample(sequence, 3));
});

test('a matched subject keeps its screen position throughout a zoom', () => {
  const sequence = createIllustratedSequence([
    { image: wide, duration: 3, anchor: [.35, .4], from: { x: .35, y: .4 }, to: { zoom: 1.5 } },
  ]);
  for (const time of [0, .5, 1, 1.5, 2, 2.5, 3]) {
    const [x, y, w, h] = sample(sequence, time)[0].crop;
    assert.ok(Math.abs((wide.width * .35 - x) / w - .35) < 1e-10);
    assert.ok(Math.abs((wide.height * .4 - y) / h - .4) < 1e-10);
  }
});

test('extreme pans stay inside the source for landscape, square and portrait output', () => {
  const sequence = createIllustratedSequence([
    { image: portrait, duration: 3, from: { x: 0, y: 1, zoom: 3 }, to: { x: 1, y: 0, zoom: 1 } },
  ]);
  for (const [width, height] of [[640, 360], [400, 400], [360, 640]]) {
    for (const time of [0, .5, 1.5, 2.5, 3]) {
      const [x, y, w, h, ...dest] = sample(sequence, time, width, height)[0].crop;
      assert.ok(x >= 0 && y >= 0 && x + w <= portrait.width + 1e-8 && y + h <= portrait.height + 1e-8);
      assert.ok(Math.abs(w / h - width / height) < 1e-10);
      assert.deepEqual(dest, [0, 0, width, height]);
    }
  }
});

test('an edge-to-edge pan starts moving on the first frame and keeps moving into the last', () => {
  const sequence = createIllustratedSequence([
    { image: wide, duration: 3, from: { x: 0, zoom: 1.5 }, to: { x: 1 } },
  ]);
  const left = t => sample(sequence, t)[0].crop[0];
  assert.ok(left(0) < left(1 / 24));
  assert.ok(left(3 - 1 / 24) < left(3));
});

test('undecoded plates, invalid motion and overlapping incoming transitions fail before rendering', () => {
  const first = { image: wide, duration: 2 };
  const second = { image: portrait, duration: 1 };
  for (const shots of [
    [], [{ ...first, duration: 0 }], [{ ...first, image: { naturalWidth: 0, width: 120, height: 50 } }],
    [{ ...first, blendIn: .3 }], [first, { ...second, blendIn: 2 }],
    [{ ...first, from: { zoom: .5 } }], [{ ...first, anchor: [-1, 1] }],
  ]) assert.throws(() => createIllustratedSequence(shots));
});

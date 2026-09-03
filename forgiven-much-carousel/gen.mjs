// Emits 10 .dc.html artboards for the "Forgiven Much?" carousel.
// Each slide: 1080x1350, full-bleed nature photo, scrim tuned per photo,
// small Helvetica text in a header/content/footer layout inside a
// hairline frame. Photos: pines.jpg, road.jpg, blooms.jpg, daisies.jpg,
// glass.jpg (900x1125 jpeg crops of the supplied originals).
import { writeFileSync } from 'node:fs';

const baseCss = `
    body { margin: 0; }
    a { color: #d6cdbf; } a:hover { color: #ffffff; }
`;

function para(t, extra = '') {
  return `<p style="margin: 0; font-size: 31px; line-height: 1.7; letter-spacing: -0.008em; font-weight: 400; color: rgba(255,255,255,0.96); text-shadow: 0 1px 26px rgba(0,0,0,0.4); ${extra}">${t}</p>`;
}

const caps = (t, extra = '') => `<span style="font-size: 19px; letter-spacing: 0.2em; text-transform: uppercase; color: rgba(255,255,255,0.6); font-weight: 500; padding-left: 0.2em; text-shadow: 0 1px 18px rgba(0,0,0,0.4); ${extra}">${t}</span>`;

function artboard({ index, photo, scrim, inner, header, footerTop }) {
  const num = String(index).padStart(2, '0');
  const [a1, a2, a3] = scrim;
  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
  <style>${baseCss}</style>
</helmet>
<div style="position: relative; width: 1080px; height: 1350px; overflow: hidden; background-color: #2e3335; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;">
  <img src="${photo}" alt="" style="position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover;">
  <div style="position: absolute; inset: 0; background: linear-gradient(180deg, rgba(10,14,15,${a1}) 0%, rgba(10,14,15,${a2}) 62%, rgba(10,14,15,${a3}) 100%);"></div>
  <div style="position: absolute; inset: 36px; border: 1px solid rgba(255,255,255,0.16);"></div>
  <div style="position: absolute; inset: 36px; display: flex; flex-direction: column; justify-content: space-between; align-items: center; text-align: center; padding: 58px 94px; box-sizing: border-box;">
    ${header ? caps(header) : '<span></span>'}
    <div style="display: flex; flex-direction: column; align-items: center;">
    ${inner}
    </div>
    <div style="display: flex; flex-direction: column; align-items: center; gap: 18px;">
      ${footerTop ? caps(footerTop) : ''}
      <span style="font-size: 18px; letter-spacing: 0.16em; color: rgba(255,255,255,0.42); font-weight: 400; padding-left: 0.16em;">${num}&#8202;/&#8202;10</span>
    </div>
  </div>
</div>
</x-dc>
</body>
</html>
`;
}

const eyebrow = (t) => `<span style="font-size: 20px; letter-spacing: 0.2em; text-transform: uppercase; color: rgba(255,255,255,0.66); font-weight: 500; padding-left: 0.2em; text-shadow: 0 1px 18px rgba(0,0,0,0.4);">${t}</span>`;
const rule = `<div style="width: 40px; height: 1px; background-color: rgba(255,255,255,0.42);"></div>`;

// scrim presets per photo brightness
const DARK = [0.2, 0.3, 0.42];
const MID = [0.3, 0.38, 0.48];
const LIGHT = [0.46, 0.52, 0.6];

const slides = [
  {
    file: 'Main.dc.html', index: 1, photo: 'pines.jpg', scrim: [0.24, 0.34, 0.46],
    header: 'A devotional', footerTop: 'Luke 7:36&ndash;50',
    inner: `
    <div style="display: flex; flex-direction: column; align-items: center; gap: 42px;">
      <h1 style="margin: 0; font-size: 72px; font-weight: 300; letter-spacing: -0.012em; color: #ffffff;">Forgiven Much?</h1>
      ${rule}
      ${para('The woman, Simon, and the debt neither of them could pay.', 'font-size: 27px; color: rgba(255,255,255,0.85); max-width: 540px;')}
    </div>`,
  },
  {
    file: 'Slide02.dc.html', index: 2, photo: 'road.jpg', scrim: DARK,
    inner: `
    <div style="display: flex; flex-direction: column; align-items: center; gap: 38px; max-width: 700px;">
      ${para('The woman walks into the room completely aware of her need for Jesus.')}
      ${para('Simon doesn&rsquo;t.')}
      ${para('Her sin was visible. His was much easier to hide.')}
    </div>`,
  },
  {
    file: 'Slide03.dc.html', index: 3, photo: 'glass.jpg', scrim: MID,
    inner: `
    <div style="display: flex; flex-direction: column; align-items: center; gap: 44px; max-width: 720px;">
      ${para('&ldquo;A certain moneylender had two debtors. One owed five hundred denarii, and the other fifty. When they could not pay, he cancelled the debt of both.&rdquo;', 'font-style: italic; font-size: 34px; line-height: 1.65;')}
      ${rule}
      ${eyebrow('Luke 7:41&ndash;42')}
    </div>`,
  },
  {
    file: 'Slide04.dc.html', index: 4, photo: 'daisies.jpg', scrim: LIGHT,
    inner: `
    <div style="display: flex; flex-direction: column; align-items: center; gap: 38px; max-width: 700px;">
      ${para('Neither could pay.', 'font-size: 38px; font-weight: 300;')}
      ${para('That&rsquo;s the part I missed for so long.')}
      ${para('The question isn&rsquo;t whether I have the most dramatic testimony in the room &mdash; it&rsquo;s whether I understand the depth of my need for a Savior.')}
    </div>`,
  },
  {
    file: 'Slide05.dc.html', index: 5, photo: 'blooms.jpg', scrim: LIGHT,
    inner: `
    <div style="display: flex; flex-direction: column; align-items: center; gap: 38px; max-width: 700px;">
      ${para('The invitation of this passage isn&rsquo;t to wish we had sinned more so we could be forgiven more.')}
      ${para('It&rsquo;s to see more clearly how much we&rsquo;ve already been forgiven.', 'font-size: 34px; font-weight: 300;')}
    </div>`,
  },
  {
    file: 'Slide06.dc.html', index: 6, photo: 'glass.jpg', scrim: MID,
    inner: `
    <div style="display: flex; flex-direction: column; align-items: center; gap: 40px; max-width: 700px;">
      ${para('Do I love Jesus like someone who has been forgiven much?')}
      <div style="display: flex; flex-direction: column; align-items: center; gap: 14px;">
        ${['Pride.', 'Self-righteousness.', 'Idolatry.', 'Ego.', 'Unbelief.'].map((w) => `<span style="font-size: 29px; letter-spacing: 0.05em; color: rgba(255,255,255,0.92); font-weight: 300;">${w}</span>`).join('\n        ')}
      </div>
      ${para('The things no one else sees.', 'color: rgba(255,255,255,0.8); font-size: 27px;')}
    </div>`,
  },
  {
    file: 'Slide07.dc.html', index: 7, photo: 'daisies.jpg', scrim: LIGHT,
    inner: `
    <div style="display: flex; flex-direction: column; align-items: center; gap: 38px; max-width: 680px;">
      ${para('Pride tells us, <em>I&rsquo;m doing pretty well.</em>')}
      ${para('Shame tells us, <em>I&rsquo;m too far gone.</em>')}
      ${rule}
      ${para('Neither is the voice of Jesus.', 'font-size: 34px; font-weight: 300;')}
    </div>`,
  },
  {
    file: 'Slide08.dc.html', index: 8, photo: 'pines.jpg', scrim: [0.24, 0.34, 0.46],
    inner: `
    <div style="display: flex; flex-direction: column; align-items: center; gap: 38px; max-width: 700px;">
      ${para('The gospel tells us the truth about both:')}
      ${para('My sin is greater than I want to admit, and His grace is greater still.', 'font-size: 36px; font-weight: 300; line-height: 1.6;')}
    </div>`,
  },
  {
    file: 'Slide09.dc.html', index: 9, photo: 'road.jpg', scrim: DARK,
    inner: `
    <div style="display: flex; flex-direction: column; align-items: center; gap: 38px; max-width: 700px;">
      ${para('So we draw near. We ask the Lord to search us.')}
      ${para('&ldquo;Create in me a clean heart, O God.&rdquo;', 'font-style: italic; font-size: 34px;')}
      ${para('Not so we can live buried beneath condemnation &mdash; but so we can live overwhelmed by grace.')}
    </div>`,
  },
  {
    file: 'Slide10.dc.html', index: 10, photo: 'blooms.jpg', scrim: LIGHT,
    inner: `
    <div style="display: flex; flex-direction: column; align-items: center; gap: 42px; max-width: 700px;">
      ${para('&ldquo;But he who is forgiven little, loves little.&rdquo;', 'font-style: italic; font-size: 34px;')}
      ${eyebrow('Luke 7:47')}
      ${rule}
      ${para('I have been forgiven much.<br>Let that reality make me love You much.', 'font-size: 31px;')}
    </div>`,
  },
];

for (const s of slides) {
  writeFileSync(s.file, artboard({
    index: s.index,
    photo: s.photo,
    scrim: s.scrim,
    inner: s.inner,
    header: s.header ?? (s.index > 1 ? 'Forgiven much' : undefined),
    footerTop: s.footerTop,
  }));
  console.log('wrote', s.file);
}

const gapX = 1180 + 120, rowY = 1350 + 200;
const canvas = {
  artboards: slides.map((s, i) => ({
    file: s.file,
    title: i === 0 ? 'Cover' : `Slide ${String(s.index).padStart(2, '0')}`,
    x: (i % 5) * gapX,
    y: Math.floor(i / 5) * rowY,
    w: 1080,
    h: 1350,
  })),
  launch: { view: 'canvas' },
};
writeFileSync('canvas.json', JSON.stringify(canvas, null, 2));
console.log('wrote canvas.json');

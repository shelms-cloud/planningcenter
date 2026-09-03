// Emits 10 .dc.html artboards for the "Forgiven Much?" carousel.
// Each slide: 1080x1350, procedural misty-nature SVG background (placeholder
// until real photos arrive), scrim, small Helvetica text.
import { writeFileSync } from 'node:fs';

const W = 1080, H = 1350;

// path helper: gentle ridge line across the canvas
function ridge(yBase, amp, seedPts) {
  let d = `M0 ${H} L0 ${yBase}`;
  const n = seedPts.length;
  for (let i = 0; i < n; i++) {
    const x = ((i + 1) / n) * W;
    const y = yBase + seedPts[i] * amp;
    const cx = x - W / n / 2;
    d += ` Q${cx.toFixed(0)} ${(yBase + (seedPts[i] + (seedPts[i - 1] ?? 0)) * amp * 0.5).toFixed(0)} ${x.toFixed(0)} ${y.toFixed(0)}`;
  }
  d += ` L${W} ${H} Z`;
  return d;
}

function scene({ skyTop, skyBot, ridges, sun, waterY, waterColor }) {
  const uid = Math.random().toString(36).slice(2, 7);
  let s = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid slice" style="position: absolute; inset: 0; width: 100%; height: 100%;" xmlns="http://www.w3.org/2000/svg">`;
  s += `<defs>`;
  s += `<linearGradient id="sky${uid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${skyTop}"></stop><stop offset="1" stop-color="${skyBot}"></stop></linearGradient>`;
  s += `<filter id="soft${uid}" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="18"></feGaussianBlur></filter>`;
  s += `<filter id="haze${uid}" x="-120%" y="-120%" width="340%" height="340%"><feGaussianBlur stdDeviation="46"></feGaussianBlur></filter>`;
  s += `<filter id="grain${uid}"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" stitchTiles="stitch"></feTurbulence><feColorMatrix type="saturate" values="0"></feColorMatrix><feComponentTransfer><feFuncA type="linear" slope="0.055"></feFuncA></feComponentTransfer><feComposite operator="in" in2="SourceGraphic"></feComposite></filter>`;
  s += `</defs>`;
  s += `<rect width="${W}" height="${H}" fill="url(#sky${uid})"></rect>`;
  if (sun) {
    s += `<circle cx="${sun.x}" cy="${sun.y}" r="${sun.r * 2.2}" fill="${sun.color}" opacity="0.18" filter="url(#haze${uid})"></circle>`;
    s += `<circle cx="${sun.x}" cy="${sun.y}" r="${sun.r}" fill="${sun.color}" opacity="0.5" filter="url(#haze${uid})"></circle>`;
  }
  ridges.forEach((r, i) => {
    const blur = i < ridges.length - 1 ? ` filter="url(#soft${uid})"` : '';
    s += `<path d="${ridge(r.y, r.amp, r.pts)}" fill="${r.color}" opacity="${r.op}"${blur}></path>`;
  });
  if (waterY) {
    s += `<rect x="-80" y="${waterY}" width="${W + 160}" height="${H - waterY + 160}" fill="${waterColor}" opacity="0.9" filter="url(#soft${uid})"></rect>`;
    s += `<rect x="-80" y="${waterY}" width="${W + 160}" height="60" fill="#ffffff" opacity="0.07" filter="url(#soft${uid})"></rect>`;
  }
  s += `<rect width="${W}" height="${H}" fill="#ffffff" filter="url(#grain${uid})" opacity="0.5"></rect>`;
  s += `</svg>`;
  return s;
}

const baseCss = `
    body { margin: 0; }
    a { color: #d6cdbf; } a:hover { color: #ffffff; }
`;

function para(t, extra = '') {
  return `<p style="margin: 0; font-size: 31px; line-height: 1.7; letter-spacing: -0.008em; font-weight: 400; color: rgba(255,255,255,0.96); ${extra}">${t}</p>`;
}

const caps = (t, extra = '') => `<span style="font-size: 19px; letter-spacing: 0.2em; text-transform: uppercase; color: rgba(255,255,255,0.6); font-weight: 500; padding-left: 0.2em; ${extra}">${t}</span>`;

function artboard({ index, sceneHtml, inner, header, footerTop }) {
  const num = String(index).padStart(2, '0');
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
  ${sceneHtml}
  <div style="position: absolute; inset: 0; background: linear-gradient(180deg, rgba(10,14,15,0.18) 0%, rgba(10,14,15,0.30) 62%, rgba(10,14,15,0.42) 100%);"></div>
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

// ---- per-slide scenes (shared muted family, varied composition) ----
const scenes = {
  cover: scene({
    skyTop: '#8d9899', skyBot: '#39454a',
    ridges: [
      { y: 620, amp: 90, pts: [0.2, -0.4, 0.1, -0.2, 0.4, -0.1], color: '#5c6b6e', op: 0.55 },
      { y: 780, amp: 110, pts: [-0.3, 0.2, -0.1, 0.35, -0.2, 0.1], color: '#46545a', op: 0.75 },
      { y: 950, amp: 80, pts: [0.15, -0.2, 0.3, -0.35, 0.1, 0.2], color: '#333f45', op: 1 },
    ],
  }),
  woman: scene({
    skyTop: '#7f8a80', skyBot: '#2f3a33',
    ridges: [
      { y: 660, amp: 100, pts: [-0.2, 0.3, -0.4, 0.1, 0.25, -0.15], color: '#55645a', op: 0.5 },
      { y: 830, amp: 90, pts: [0.3, -0.15, 0.2, -0.3, 0.1, 0.3], color: '#404f46', op: 0.8 },
      { y: 1000, amp: 70, pts: [-0.1, 0.25, -0.3, 0.15, -0.2, 0.05], color: '#2c372f', op: 1 },
    ],
  }),
  verse1: scene({
    skyTop: '#95998f', skyBot: '#4a5350',
    sun: { x: 540, y: 470, r: 90, color: '#e8e3d5' },
    waterY: 760, waterColor: '#39443f',
    ridges: [
      { y: 700, amp: 50, pts: [0.1, -0.2, 0.15, -0.1, 0.2, -0.05], color: '#5a6560', op: 0.55 },
    ],
  }),
  neither: scene({
    skyTop: '#8a8d8e', skyBot: '#3b3f41',
    ridges: [
      { y: 700, amp: 60, pts: [0.1, -0.15, 0.2, -0.25, 0.05, 0.15], color: '#5f6567', op: 0.45 },
      { y: 880, amp: 90, pts: [-0.25, 0.15, -0.1, 0.3, -0.2, 0.1], color: '#484e50', op: 0.8 },
      { y: 1040, amp: 60, pts: [0.2, -0.1, 0.15, -0.2, 0.25, -0.05], color: '#323738', op: 1 },
    ],
  }),
  invitation: scene({
    skyTop: '#9aa192', skyBot: '#454e42',
    sun: { x: 760, y: 380, r: 70, color: '#f0ead8' },
    ridges: [
      { y: 640, amp: 100, pts: [0.25, -0.3, 0.15, -0.15, 0.35, -0.2], color: '#68715f', op: 0.5 },
      { y: 820, amp: 110, pts: [-0.2, 0.25, -0.35, 0.1, -0.15, 0.3], color: '#525b4c', op: 0.75 },
      { y: 990, amp: 80, pts: [0.1, -0.25, 0.2, -0.1, 0.05, 0.2], color: '#3a4237', op: 1 },
    ],
  }),
  hidden: scene({
    skyTop: '#6f7a7a', skyBot: '#28312f',
    ridges: [
      { y: 600, amp: 120, pts: [-0.3, 0.15, -0.2, 0.35, -0.1, 0.2], color: '#4c5a57', op: 0.5 },
      { y: 790, amp: 100, pts: [0.2, -0.3, 0.1, -0.15, 0.3, -0.2], color: '#3a4744', op: 0.8 },
      { y: 970, amp: 70, pts: [-0.15, 0.2, -0.25, 0.1, -0.05, 0.25], color: '#273230', op: 1 },
    ],
  }),
  voices: scene({
    skyTop: '#a3a6a2', skyBot: '#565c58',
    ridges: [
      { y: 750, amp: 50, pts: [0.1, -0.1, 0.15, -0.2, 0.1, -0.05], color: '#787e79', op: 0.4 },
      { y: 920, amp: 70, pts: [-0.2, 0.1, -0.1, 0.25, -0.15, 0.05], color: '#606662', op: 0.75 },
      { y: 1070, amp: 50, pts: [0.15, -0.05, 0.1, -0.15, 0.2, -0.1], color: '#484e4a', op: 1 },
    ],
  }),
  gospel: scene({
    skyTop: '#8b95a0', skyBot: '#37424c',
    sun: { x: 330, y: 420, r: 80, color: '#e5e8ea' },
    ridges: [
      { y: 680, amp: 110, pts: [0.3, -0.2, 0.25, -0.35, 0.15, 0.1], color: '#5a6772', op: 0.5 },
      { y: 860, amp: 90, pts: [-0.15, 0.3, -0.25, 0.15, -0.1, 0.25], color: '#465360', op: 0.8 },
      { y: 1020, amp: 70, pts: [0.1, -0.2, 0.05, -0.1, 0.2, -0.15], color: '#333e49', op: 1 },
    ],
  }),
  search: scene({
    skyTop: '#93887e', skyBot: '#443e39',
    sun: { x: 540, y: 500, r: 100, color: '#f2e2c8' },
    waterY: 820, waterColor: '#3c3833',
    ridges: [
      { y: 740, amp: 60, pts: [-0.15, 0.1, -0.2, 0.05, -0.1, 0.15], color: '#5f574e', op: 0.6 },
    ],
  }),
  close: scene({
    skyTop: '#5d6a6e', skyBot: '#1f292d',
    sun: { x: 540, y: 400, r: 60, color: '#dfe4e4' },
    ridges: [
      { y: 700, amp: 90, pts: [0.2, -0.25, 0.1, -0.1, 0.3, -0.15], color: '#3d4a4f', op: 0.55 },
      { y: 880, amp: 100, pts: [-0.2, 0.15, -0.3, 0.2, -0.1, 0.1], color: '#2d383d', op: 0.8 },
      { y: 1050, amp: 60, pts: [0.1, -0.15, 0.2, -0.05, 0.05, 0.15], color: '#1d2529', op: 1 },
    ],
  }),
};

const eyebrow = (t) => `<span style="font-size: 20px; letter-spacing: 0.2em; text-transform: uppercase; color: rgba(255,255,255,0.66); font-weight: 500; padding-left: 0.2em;">${t}</span>`;
const rule = `<div style="width: 40px; height: 1px; background-color: rgba(255,255,255,0.42);"></div>`;

const slides = [
  {
    file: 'Main.dc.html', index: 1, scene: scenes.cover,
    header: 'A devotional', footerTop: 'Luke 7:36&ndash;50',
    inner: `
    <div style="display: flex; flex-direction: column; align-items: center; gap: 42px;">
      <h1 style="margin: 0; font-size: 72px; font-weight: 300; letter-spacing: -0.012em; color: #ffffff;">Forgiven Much?</h1>
      ${rule}
      ${para('The woman, Simon, and the debt neither of them could pay.', 'font-size: 27px; color: rgba(255,255,255,0.85); max-width: 540px;')}
    </div>`,
  },
  {
    file: 'Slide02.dc.html', index: 2, scene: scenes.woman,
    inner: `
    <div style="display: flex; flex-direction: column; align-items: center; gap: 38px; max-width: 700px;">
      ${para('The woman walks into the room completely aware of her need for Jesus.')}
      ${para('Simon doesn&rsquo;t.')}
      ${para('Her sin was visible. His was much easier to hide.')}
    </div>`,
  },
  {
    file: 'Slide03.dc.html', index: 3, scene: scenes.verse1,
    inner: `
    <div style="display: flex; flex-direction: column; align-items: center; gap: 44px; max-width: 720px;">
      ${para('&ldquo;A certain moneylender had two debtors. One owed five hundred denarii, and the other fifty. When they could not pay, he cancelled the debt of both.&rdquo;', 'font-style: italic; font-size: 34px; line-height: 1.65;')}
      ${rule}
      ${eyebrow('Luke 7:41&ndash;42')}
    </div>`,
  },
  {
    file: 'Slide04.dc.html', index: 4, scene: scenes.neither,
    inner: `
    <div style="display: flex; flex-direction: column; align-items: center; gap: 38px; max-width: 700px;">
      ${para('Neither could pay.', 'font-size: 38px; font-weight: 300;')}
      ${para('That&rsquo;s the part I missed for so long.')}
      ${para('The question isn&rsquo;t whether I have the most dramatic testimony in the room &mdash; it&rsquo;s whether I understand the depth of my need for a Savior.')}
    </div>`,
  },
  {
    file: 'Slide05.dc.html', index: 5, scene: scenes.invitation,
    inner: `
    <div style="display: flex; flex-direction: column; align-items: center; gap: 38px; max-width: 700px;">
      ${para('The invitation of this passage isn&rsquo;t to wish we had sinned more so we could be forgiven more.')}
      ${para('It&rsquo;s to see more clearly how much we&rsquo;ve already been forgiven.', 'font-size: 34px; font-weight: 300;')}
    </div>`,
  },
  {
    file: 'Slide06.dc.html', index: 6, scene: scenes.hidden,
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
    file: 'Slide07.dc.html', index: 7, scene: scenes.voices,
    inner: `
    <div style="display: flex; flex-direction: column; align-items: center; gap: 38px; max-width: 680px;">
      ${para('Pride tells us, <em>I&rsquo;m doing pretty well.</em>')}
      ${para('Shame tells us, <em>I&rsquo;m too far gone.</em>')}
      ${rule}
      ${para('Neither is the voice of Jesus.', 'font-size: 34px; font-weight: 300;')}
    </div>`,
  },
  {
    file: 'Slide08.dc.html', index: 8, scene: scenes.gospel,
    inner: `
    <div style="display: flex; flex-direction: column; align-items: center; gap: 38px; max-width: 700px;">
      ${para('The gospel tells us the truth about both:')}
      ${para('My sin is greater than I want to admit, and His grace is greater still.', 'font-size: 36px; font-weight: 300; line-height: 1.6;')}
    </div>`,
  },
  {
    file: 'Slide09.dc.html', index: 9, scene: scenes.search,
    inner: `
    <div style="display: flex; flex-direction: column; align-items: center; gap: 38px; max-width: 700px;">
      ${para('So we draw near. We ask the Lord to search us.')}
      ${para('&ldquo;Create in me a clean heart, O God.&rdquo;', 'font-style: italic; font-size: 34px;')}
      ${para('Not so we can live buried beneath condemnation &mdash; but so we can live overwhelmed by grace.')}
    </div>`,
  },
  {
    file: 'Slide10.dc.html', index: 10, scene: scenes.close,
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
    sceneHtml: s.scene,
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

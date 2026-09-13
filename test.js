const PptxGenJS = require('pptxgenjs');

const pres = new PptxGenJS();
pres.layout = 'LAYOUT_16x9';
pres.defineLayout({ name: 'TITLE', master: 'BLANK' });

// Color Palette
const colors = {
  dark: '1F4E78',
  primary: '4472C4',
  secondary: '70AD47',
  accent: 'FF6B6B',
  light: 'F2F2F2',
  white: 'FFFFFF',
  darkText: '1A1A1A',
  gray: '7F7F7F',
  success: '00B050',
  warning: 'FFC000'
};

// Helper function to create title slide
function addTitleSlide(pres, title, subtitle, bgColor = colors.dark) {
  const slide = pres.addSlide();
  slide.background = { color: bgColor };
  
  slide.addText(title, {
    x: 0.5, y: 1.8, w: 9, h: 1.2,
    fontSize: 54, bold: true, color: colors.white,
    align: 'center', isTextBox: true
  });
  
  slide.addText(subtitle, {
    x: 0.5, y: 3.2, w: 9, h: 0.8,
    fontSize: 28, color: colors.light,
    align: 'center', isTextBox: true
  });
  
  return slide;
}

// Helper function for content slides
function addContentSlide(pres, title, bgColor = colors.white, titleBg = colors.primary) {
  const slide = pres.addSlide();
  slide.background = { color: bgColor };
  
  // Title bar
  slide.addShape(pres.ShapeType.rectangle, {
    x: 0, y: 0, w: 10, h: 0.8,
    fill: { color: titleBg },
    line: { type: 'none' }
  });
  
  slide.addText(title, {
    x: 0.3, y: 0.1, w: 9.4, h: 0.6,
    fontSize: 40, bold: true, color: colors.white,
    align: 'left', isTextBox: true
  });
  
  return slide;
}

// ===== SLIDE 1: TITLE =====
addTitleSlide(pres, 'SovereignGuard', 'AI Red Team–Blue Team Payment Security Laboratory\nMasterCard Innovation Challenge 2026', colors.dark);

// ===== SLIDE 2: IDEATION & PROBLEM =====
let slide = addContentSlide(pres, '1. Ideation & Problem Statement');
slide.addText('The Fundamental Challenge', {
  x: 0.5, y: 1.2, w: 9, h: 0.4,
  fontSize: 24, bold: true, color: colors.dark, isTextBox: true
});

slide.addText(
  '✗ Traditional fraud defense is REACTIVE\n' +
  '  • Rules written AFTER patterns observed\n' +
  '  • Models trained on HISTORICAL fraud\n' +
  '  • Defenses updated AFTER attackers find weakness',
  {
    x: 0.7, y: 1.8, w: 8.6, h: 1.2,
    fontSize: 16, color: colors.darkText, isTextBox: true
  }
);

slide.addText('Generative AI Changes Everything', {
  x: 0.5, y: 3.2, w: 9, h: 0.4,
  fontSize: 24, bold: true, color: colors.accent, isTextBox: true
});

slide.addText(
  '→ Collapses cost of creating NEW attack VARIANTS\n' +
  '→ Shift from few templates to MANY low-volume personalized attacks\n' +
  '→ Autonomous, minute-scale iteration against the defense\n' +
  '→ Models that were 99% accurate become 26% accurate when attacked',
  {
    x: 0.7, y: 3.8, w: 8.6, h: 1.2,
    fontSize: 15, color: colors.darkText, isTextBox: true
  }
);

// ===== SLIDE 3: MARKET REALITY =====
slide = addContentSlide(pres, 'Market Reality: The Numbers');

slide.addShape(pres.ShapeType.rectangle, {
  x: 0.5, y: 1.2, w: 4.4, h: 1.4,
  fill: { color: colors.light },
  line: { color: colors.primary, width: 2 }
});

slide.addText(
  'Voice-Clone / Deepfake Attacks\n' +
  '+94% YoY (UK Banking 2025-26)\n' +
  '7% of fraud attempts screened',
  {
    x: 0.7, y: 1.3, w: 4, h: 1.2,
    fontSize: 14, bold: true, color: colors.primary, align: 'center', isTextBox: true
  }
);

slide.addShape(pres.ShapeType.rectangle, {
  x: 5.1, y: 1.2, w: 4.4, h: 1.4,
  fill: { color: colors.light },
  line: { color: colors.accent, width: 2 }
});

slide.addText(
  'KYC Liveness Bypass\n' +
  '+1,151% in H2 2025\n' +
  '4× jump in deepfake detection',
  {
    x: 5.3, y: 1.3, w: 4, h: 1.2,
    fontSize: 14, bold: true, color: colors.accent, align: 'center', isTextBox: true
  }
);

slide.addShape(pres.ShapeType.rectangle, {
  x: 0.5, y: 3.0, w: 4.4, h: 1.4,
  fill: { color: colors.light },
  line: { color: colors.secondary, width: 2 }
});

slide.addText(
  'Authorized Push Payment (APP)\n' +
  'Fastest-growing $ category\n' +
  'All auth controls show GREEN',
  {
    x: 0.7, y: 3.1, w: 4, h: 1.2,
    fontSize: 14, bold: true, color: colors.secondary, align: 'center', isTextBox: true
  }
);

slide.addShape(pres.ShapeType.rectangle, {
  x: 5.1, y: 3.0, w: 4.4, h: 1.4,
  fill: { color: colors.light },
  line: { color: colors.warning, width: 2 }
});

slide.addText(
  'Agentic Fraud (2026)\n' +
  'Attacks observe defense → learn boundary → act autonomously\n' +
  'Polymorphic, personalized',
  {
    x: 5.3, y: 3.1, w: 4, h: 1.2,
    fontSize: 14, bold: true, color: colors.warning, align: 'center', isTextBox: true
  }
);

// ===== SLIDE 4: SOLUTION PROPOSED =====
slide = addContentSlide(pres, '2. Solution Proposed: SovereignGuard');

slide.addText('Core Philosophy', {
  x: 0.5, y: 1.2, w: 9, h: 0.4,
  fontSize: 22, bold: true, color: colors.dark, isTextBox: true
});

slide.addShape(pres.ShapeType.rectangle, {
  x: 0.5, y: 1.7, w: 9, h: 0.7,
  fill: { color: colors.primary },
  line: { type: 'none' }
});

slide.addText(
  '"Don\'t wait for criminals to test your fraud system. Test it yourself first."',
  {
    x: 0.7, y: 1.8, w: 8.6, h: 0.5,
    fontSize: 18, bold: true, color: colors.white, align: 'center', italic: true, isTextBox: true
  }
);

slide.addText('A Continuous Adversarial Stress-Testing Lab', {
  x: 0.5, y: 2.6, w: 9, h: 0.4,
  fontSize: 20, bold: true, color: colors.secondary, isTextBox: true
});

slide.addText(
  '→ Generate realistic synthetic payment ecosystem (~2,000 customers, 360k transactions)\n' +
  '→ Inject fraud from 7 attack families with 4 difficulty levels\n' +
  '→ Pit a from-scratch ML detector against them\n' +
  '→ Identify weaknesses through gap analysis\n' +
  '→ Generate targeted adversarial attacks\n' +
  '→ Retrain & measure improvement on NEVER-SEEN attacks\n' +
  '→ Prove the loop works with honest numbers',
  {
    x: 0.7, y: 3.2, w: 8.6, h: 1.8,
    fontSize: 15, color: colors.darkText, isTextBox: true
  }
);

// ===== SLIDE 5: HERO LOOP =====
slide = addContentSlide(pres, 'The Hero Loop: IDENTIFY → GENERATE → ATTACK → DETECT → EXPLAIN → ADAPT → RETEST');

const stages = ['IDENTIFY', 'GENERATE', 'ATTACK', 'DETECT', 'EXPLAIN', 'ADAPT', 'RETEST'];
const stageColors = [colors.primary, colors.secondary, colors.accent, colors.warning, colors.primary, colors.secondary, colors.accent];
const stageX = [0.5, 1.9, 3.3, 4.7, 6.1, 7.5, 8.9];

stages.forEach((stage, i) => {
  slide.addShape(pres.ShapeType.rectangle, {
    x: stageX[i], y: 1.3, w: 1.2, h: 0.6,
    fill: { color: stageColors[i] },
    line: { type: 'none' }
  });
  
  slide.addText(stage, {
    x: stageX[i], y: 1.35, w: 1.2, h: 0.5,
    fontSize: 11, bold: true, color: colors.white, align: 'center', isTextBox: true
  });
  
  if (i < stages.length - 1) {
    slide.addText('→', {
      x: stageX[i] + 1.15, y: 1.35, w: 0.3, h: 0.5,
      fontSize: 20, color: colors.primary, align: 'center', isTextBox: true
    });
  }
});

const descriptions = [
  { title: 'Attack Knowledge Base', text: '7-family taxonomy (Account Takeover, Transaction Manipulation, Synthetic Identity, Merchant Fraud, Phishing, Social Engineering, Multi-Stage)' },
  { title: 'Synthetic World', text: '7 personas, 14 categories, 20 cities, realistic habits, non-zero life-event rates' },
  { title: 'Red Team AI', text: '4 difficulty levels, multi-stage sequences, spliced into victim timelines' },
  { title: 'Blue Team ML', text: '83 causal features, GBDT + RF, risk bands, reason codes' },
  { title: 'TreeSHAP', text: 'Verified to 2.7e-08 vs Shapley definition, attributable decisions' },
  { title: 'Gap Analysis', text: '10 evasion hypotheses ranked by lift, identify structural weakness' },
  { title: 'Retest', text: 'Dual-batch anti-cheat, matched FPR, regression reporting' }
];

descriptions.forEach((desc, i) => {
  slide.addText(desc.title, {
    x: stageX[i], y: 2.2, w: 1.2, h: 0.3,
    fontSize: 11, bold: true, color: stageColors[i], align: 'center', isTextBox: true
  });
  
  slide.addText(desc.text, {
    x: stageX[i] - 0.15, y: 2.55, w: 1.4, h: 1.3,
    fontSize: 8, color: colors.gray, align: 'center', isTextBox: true
  });
});

// ===== SLIDE 6: HEADLINE RESULT =====
slide = addContentSlide(pres, 'Headline Result: Measured Improvement');

slide.addShape(pres.ShapeType.rectangle, {
  x: 0.5, y: 1.3, w: 9, h: 2.5,
  fill: { color: colors.light },
  line: { color: colors.success, width: 3 }
});

slide.addText('Adaptive Loop at Matched False Positive Rate (1.0%)', {
  x: 0.7, y: 1.5, w: 8.6, h: 0.3,
  fontSize: 18, bold: true, color: colors.success, isTextBox: true
});

const metrics = [
  { label: 'Recall (held-out adversarial)', before: '22.0%', after: '35.5%', change: '+13.5 pts' },
  { label: 'F1-Score', before: '0.357', after: '0.519', change: '+16.2 pts' },
  { label: 'Attacks Missed', before: '2,863', after: '2,367', change: '−496' },
  { label: 'False Positive Rate', before: '0.991%', after: '0.991%', change: 'matched' }
];

let y = 2.0;
metrics.forEach(m => {
  slide.addText(m.label, {
    x: 0.8, y: y, w: 3.5, h: 0.35,
    fontSize: 14, bold: true, color: colors.darkText, isTextBox: true
  });
  slide.addText(m.before + ' → ' + m.after, {
    x: 4.5, y: y, w: 2, h: 0.35,
    fontSize: 14, color: colors.primary, isTextBox: true
  });
  slide.addText(m.change, {
    x: 6.8, y: y, w: 1.8, h: 0.35,
    fontSize: 14, bold: true, color: colors.success, isTextBox: true
  });
  y += 0.35;
});

slide.addText('Honest Regression on Original Distribution: 51.4% → 40.3% (−11.1 pts)', {
  x: 0.8, y: 3.6, w: 8.4, h: 0.3,
  fontSize: 13, italic: true, color: colors.accent, isTextBox: true
});

slide.addText('↓ The trade-off is REAL and INTENTIONAL — exactly what a stress-testing tool should surface.', {
  x: 0.8, y: 4.0, w: 8.4, h: 0.4,
  fontSize: 12, color: colors.gray, isTextBox: true
});

// ===== SLIDE 7: SOLUTION FEATURES VS EXISTING =====
slide = addContentSlide(pres, '3. Solution Features: What\'s New vs What Exists');

slide.addShape(pres.ShapeType.rectangle, {
  x: 0.5, y: 1.2, w: 4.3, h: 0.5,
  fill: { color: colors.gray },
  line: { type: 'none' }
});
slide.addText('Traditional Approaches', {
  x: 0.7, y: 1.25, w: 3.9, h: 0.4,
  fontSize: 16, bold: true, color: colors.white, isTextBox: true
});

slide.addShape(pres.ShapeType.rectangle, {
  x: 5.2, y: 1.2, w: 4.3, h: 0.5,
  fill: { color: colors.success },
  line: { type: 'none' }
});
slide.addText('SovereignGuard Innovation', {
  x: 5.4, y: 1.25, w: 3.9, h: 0.4,
  fontSize: 16, bold: true, color: colors.white, isTextBox: true
});

const comparison = [
  { old: 'Attack source: Scripts', new: 'Parameterized 7-family taxonomy' },
  { old: 'GenAI awareness: None', new: 'Attack role of GenAI documented' },
  { old: 'Evasion levels: None', new: '4 levels (EASY→ADVERSARIAL)' },
  { old: 'Adaptation: Manual', new: 'Automated adversarial loop' },
  { old: 'Explainability: Opaque', new: 'TreeSHAP (2.7e-08 vs definition)' },
  { old: 'Evaluation: Same distribution', new: 'Dual independent batches' },
  { old: 'Honest about trade-offs: No', new: 'Yes—regression always reported' },
  { old: 'Features: 5-20', new: '83 strictly-causal, audited' }
];

let yPos = 1.9;
comparison.forEach(comp => {
  slide.addText('✗ ' + comp.old, {
    x: 0.7, y: yPos, w: 4.0, h: 0.25,
    fontSize: 12, color: colors.gray, isTextBox: true
  });
  slide.addText('✓ ' + comp.new, {
    x: 5.4, y: yPos, w: 4.0, h: 0.25,
    fontSize: 12, color: colors.success, isTextBox: true
  });
  yPos += 0.32;
});

// ===== SLIDE 8: UNIQUE TECHNOLOGY STACK =====
slide = addContentSlide(pres, '4. Unique Technology Stack');

slide.addText('Why From-Scratch ML? Air-gapped Environment → Opportunity', {
  x: 0.5, y: 1.2, w: 9, h: 0.4,
  fontSize: 18, bold: true, color: colors.accent, isTextBox: true
});

const techStack = [
  { category: 'ML Core', items: 'Histogram GBDT (98.6% of Bayes-optimal) + Random Forest + TreeSHAP\nAll in numpy — verified vs theoretical bounds' },
  { category: 'Runtime', items: 'Python 3.9+ | numpy | pandas (ONLY 2 deps)' },
  { category: 'Data', items: 'SQLite (PostgreSQL DDL included) | pickle snapshots' },
  { category: 'API', items: 'stdlib http.server REST | JSON | SSE streams' },
  { category: 'Frontend', items: 'Next.js 14 | React | Plain JS (no TypeScript)' },
  { category: 'DevOps', items: 'Docker Compose | shell CLI | GitHub Actions' }
];

let y = 1.8;
techStack.forEach(tech => {
  slide.addShape(pres.ShapeType.rectangle, {
    x: 0.5, y: y, w: 1.3, h: 0.35,
    fill: { color: colors.primary },
    line: { type: 'none' }
  });
  slide.addText(tech.category, {
    x: 0.6, y: y + 0.05, w: 1.1, h: 0.25,
    fontSize: 12, bold: true, color: colors.white, align: 'center', isTextBox: true
  });
  
  slide.addText(tech.items, {
    x: 1.95, y: y, w: 7.55, h: 0.35,
    fontSize: 12, color: colors.darkText, isTextBox: true
  });
  
  y += 0.42;
});

slide.addText('Code: ~7.8k LOC Python | 92 Unit Tests (all pass) | 14 End-to-End Verification Stages (all pass)', {
  x: 0.5, y: 4.1, w: 9, h: 0.4,
  fontSize: 12, italic: true, color: colors.gray, isTextBox: true
});

// ===== SLIDE 9: ATTACK FAMILY SEGREGATION =====
slide = addContentSlide(pres, '5. Attack Family Segregation: 7 Current, 13 Planned');

slide.addText('Four Orthogonal Dimensions', {
  x: 0.5, y: 1.2, w: 9, h: 0.35,
  fontSize: 18, bold: true, color: colors.dark, isTextBox: true
});

const dimensions = [
  { dim: '1. Family', desc: 'WHAT is attacked (7→13 families parameterised)' },
  { dim: '2. Difficulty', desc: 'HOW well attacker hides (EASY/MEDIUM/HARD/ADVERSARIAL)' },
  { dim: '3. Victim Context', desc: 'WHO is targeted (persona, geography, merchant pool)' },
  { dim: '4. Stage Sequence', desc: 'HOW it unfolds over time (kill-chain per family)' }
];

let yPos = 1.75;
dimensions.forEach((d, i) => {
  slide.addShape(pres.ShapeType.rectangle, {
    x: 0.5, y: yPos, w: 0.4, h: 0.3,
    fill: { color: stageColors[i % stageColors.length] },
    line: { type: 'none' }
  });
  slide.addText(d.dim, {
    x: 1.0, y: yPos, w: 2.0, h: 0.3,
    fontSize: 13, bold: true, color: colors.dark, isTextBox: true
  });
  slide.addText(d.desc, {
    x: 3.1, y: yPos, w: 6.4, h: 0.3,
    fontSize: 13, color: colors.gray, isTextBox: true
  });
  yPos += 0.5;
});

slide.addText('7 Current Families', {
  x: 0.5, y: 3.8, w: 9, h: 0.3,
  fontSize: 16, bold: true, color: colors.primary, isTextBox: true
});

slide.addText(
  'Account Takeover (CRITICAL) • Transaction Manipulation (HIGH) • Synthetic Identity (HIGH)\n' +
  'Merchant Fraud (HIGH) • Phishing/Payment Link (HIGH) • Social Engineering (CRITICAL) • Multi-Stage (CRITICAL)',
  {
    x: 0.7, y: 4.15, w: 8.6, h: 0.5,
    fontSize: 12, color: colors.darkText, isTextBox: true
  }
);

slide.addText('Planned GenAI-Native Families (+6)', {
  x: 0.5, y: 4.8, w: 9, h: 0.3,
  fontSize: 16, bold: true, color: colors.accent, isTextBox: true
});

slide.addText(
  'Deepfake ATO • Conversational Agent Vishing • Agentic APP Injection • Deepfake KYC • Mule Network Orchestration • Invoice-Timed BEC',
  {
    x: 0.7, y: 5.15, w: 8.6, h: 0.35,
    fontSize: 12, color: colors.darkText, isTextBox: true
  }
);

// ===== SLIDE 10: SYNTHETIC DATA GENERATION =====
slide = addContentSlide(pres, '6. Synthetic Data Generation: Privacy-Safe, Reproducible');

slide.addText('Why Synthetic?', {
  x: 0.5, y: 1.2, w: 9, h: 0.3,
  fontSize: 18, bold: true, color: colors.dark, isTextBox: true
});

slide.addText('Real data is private, sparse, labeled after loss. Synthetic data is fully controllable, deterministic, zero PII.', {
  x: 0.7, y: 1.6, w: 8.6, h: 0.3,
  fontSize: 13, color: colors.gray, isTextBox: true
});

slide.addText('Three-Layer Architecture', {
  x: 0.5, y: 2.1, w: 9, h: 0.3,
  fontSize: 16, bold: true, color: colors.primary, isTextBox: true
});

const layers = [
  { name: 'Layer 1: Population', content: '7 personas (student, young prof, family, senior, gig, business, HNW)\n14 categories | 20 cities | Lognormal amounts | Behavior habits' },
  { name: 'Layer 2: Legitimate Traffic', content: 'Hour-curve simulation | 62/38 amount blend | Life events\n~98.4% approved | LEGIT_EVENT_RATES non-zero' },
  { name: 'Layer 3: The Honesty Rule', content: 'Real customers change phones, travel, add payees, mistype passwords\nif these rates were 0%, feature becomes perfect fraud oracle\nNon-zero rates guard against leakage' }
];

let yPos = 2.5;
layers.forEach(layer => {
  slide.addShape(pres.ShapeType.rectangle, {
    x: 0.5, y: yPos, w: 9, h: 0.85,
    fill: { color: colors.light },
    line: { color: colors.primary, width: 1 }
  });
  
  slide.addText(layer.name, {
    x: 0.7, y: yPos + 0.08, w: 8.6, h: 0.25,
    fontSize: 13, bold: true, color: colors.primary, isTextBox: true
  });
  
  slide.addText(layer.content, {
    x: 0.7, y: yPos + 0.35, w: 8.6, h: 0.4,
    fontSize: 11, color: colors.darkText, isTextBox: true
  });
  
  yPos += 1.0;
});

// ===== SLIDE 11: ATTACK INJECTION =====
slide = addContentSlide(pres, 'Attack Injection: "Earned, Not Stamped"');

slide.addText('Core Insight', {
  x: 0.5, y: 1.2, w: 9, h: 0.3,
  fontSize: 18, bold: true, color: colors.dark, isTextBox: true
});

slide.addShape(pres.ShapeType.rectangle, {
  x: 0.5, y: 1.6, w: 9, h: 1.2,
  fill: { color: colors.light },
  line: { color: colors.accent, width: 2 }
});

slide.addText(
  'Attack sequences are spliced into victim timelines.\n' +
  'ALL features are recomputed over the MERGED stream.\n' +
  'An ADVERSARIAL attack\'s velocity, device-novelty, beneficiary-age are genuinely EARNED from history.\n' +
  'So HARD attacks are actually HARD.',
  {
    x: 0.7, y: 1.75, w: 8.6, h: 1.0,
    fontSize: 13, bold: true, color: colors.accent, align: 'center', isTextBox: true
  }
);

slide.addText('Difficulty Gradient (Converges toward Legitimate Behavior)', {
  x: 0.5, y: 3.0, w: 9, h: 0.3,
  fontSize: 16, bold: true, color: colors.primary, isTextBox: true
});

const diffTable = [
  { feature: 'Amount vs median', legit: '2.0×', easy: '15.7×', medium: '7.2×', hard: '2.8×' },
  { feature: 'New device rate', legit: '0.019', easy: '0.075', medium: '0.063', hard: '0.023' },
  { feature: 'Distance (km)', legit: '27', easy: '835', medium: '226', hard: '92' },
  { feature: 'Amount % credit limit', legit: '5.7%', easy: '42.8%', medium: '20.3%', hard: '8.1%' }
];

let yPos = 3.5;
slide.addText('Feature', {
  x: 0.6, y: yPos, w: 2.5, h: 0.3,
  fontSize: 12, bold: true, color: colors.white, isTextBox: true
});
slide.addText('LEGIT', {
  x: 3.2, y: yPos, w: 1.2, h: 0.3,
  fontSize: 12, bold: true, color: colors.white, isTextBox: true
});
slide.addText('EASY', {
  x: 4.5, y: yPos, w: 1.2, h: 0.3,
  fontSize: 12, bold: true, color: colors.white, isTextBox: true
});
slide.addText('MEDIUM', {
  x: 5.8, y: yPos, w: 1.2, h: 0.3,
  fontSize: 12, bold: true, color: colors.white, isTextBox: true
});
slide.addText('HARD', {
  x: 7.1, y: yPos, w: 1.2, h: 0.3,
  fontSize: 12, bold: true, color: colors.white, isTextBox: true
});

// Add header background
slide.addShape(pres.ShapeType.rectangle, {
  x: 0.5, y: 3.5, w: 8, h: 0.3,
  fill: { color: colors.primary },
  line: { type: 'none' }
});

yPos = 3.85;
diffTable.forEach(row => {
  slide.addText(row.feature, {
    x: 0.6, y: yPos, w: 2.5, h: 0.25,
    fontSize: 11, color: colors.darkText, isTextBox: true
  });
  slide.addText(row.legit, {
    x: 3.3, y: yPos, w: 1.1, h: 0.25,
    fontSize: 11, color: colors.darkText, align: 'center', isTextBox: true
  });
  slide.addText(row.easy, {
    x: 4.5, y: yPos, w: 1.1, h: 0.25,
    fontSize: 11, color: colors.darkText, align: 'center', isTextBox: true
  });
  slide.addText(row.medium, {
    x: 5.8, y: yPos, w: 1.1, h: 0.25,
    fontSize: 11, color: colors.darkText, align: 'center', isTextBox: true
  });
  slide.addText(row.hard, {
    x: 7.1, y: yPos, w: 1.1, h: 0.25,
    fontSize: 11, color: colors.darkText, align: 'center', isTextBox: true
  });
  yPos += 0.3;
});

// ===== SLIDE 12: SCALE PROFILES =====
slide = addContentSlide(pres, 'Deterministic Scale Profiles');

slide.addText('All profiles share one seed (20260823) + config fingerprint. Results from larger scales are load-bearing.', {
  x: 0.5, y: 1.2, w: 9, h: 0.4,
  fontSize: 14, color: colors.gray, isTextBox: true
});

const scales = [
  { name: 'nano', customers: '300', merchants: '200', days: '21', txns: '~16k', use: 'Iteration speed' },
  { name: 'tiny', customers: '400', merchants: '300', days: '30', txns: '~31k', use: 'Testing' },
  { name: 'demo', customers: '2,000', merchants: '1,200', days: '45', txns: '~234k', use: 'DEFAULT, load-bearing' },
  { name: 'large', customers: '10,000', merchants: '4,000', days: '60', txns: '~1.6M', use: 'Scale testing' },
  { name: 'full', customers: '100,000', merchants: '20,000', days: '90', txns: '~23M', use: 'Enterprise' }
];

let yPos = 2.0;
scales.forEach((scale, idx) => {
  const bgColor = scale.name === 'demo' ? colors.light : colors.white;
  const borderColor = scale.name === 'demo' ? colors.success : colors.primary;
  
  slide.addShape(pres.ShapeType.rectangle, {
    x: 0.5, y: yPos, w: 9, h: 0.45,
    fill: { color: bgColor },
    line: { color: borderColor, width: scale.name === 'demo' ? 2 : 1 }
  });
  
  slide.addText(scale.name.toUpperCase(), {
    x: 0.7, y: yPos + 0.08, w: 1.2, h: 0.3,
    fontSize: 12, bold: true, color: colors.primary, isTextBox: true
  });
  
  slide.addText(scale.customers, {
    x: 2.0, y: yPos + 0.08, w: 1.2, h: 0.3,
    fontSize: 11, color: colors.darkText, isTextBox: true
  });
  
  slide.addText(scale.merchants, {
    x: 3.3, y: yPos + 0.08, w: 1.2, h: 0.3,
    fontSize: 11, color: colors.darkText, isTextBox: true
  });
  
  slide.addText(scale.txns, {
    x: 4.6, y: yPos + 0.08, w: 1.4, h: 0.3,
    fontSize: 11, color: colors.darkText, isTextBox: true
  });
  
  slide.addText(scale.use, {
    x: 6.2, y: yPos + 0.08, w: 3.3, h: 0.3,
    fontSize: 11, color: colors.gray, isTextBox: true
  });
  
  yPos += 0.52;
});

// ===== SLIDE 13: FEATURE ENGINEERING =====
slide = addContentSlide(pres, '7. Technology: 83 Strictly-Causal Features');

slide.addText('Organized in 10 Dimensions | Streaming Pass | Structural Causality', {
  x: 0.5, y: 1.2, w: 9, h: 0.3,
  fontSize: 16, bold: true, color: colors.primary, isTextBox: true
});

const featureDims = [
  { dim: 'Amount', count: 9, examples: 'Ratio vs median, 7d max, z-score, round-number flag' },
  { dim: 'Velocity', count: 13, examples: 'Txn in 10m/1h/24h/7d, distinct merchants/devices/cities' },
  { dim: 'Device', count: 7, examples: 'New-device flag, age, txn count, emulator/root' },
  { dim: 'Location', count: 6, examples: 'Distance from home, implied speed, high-risk city' },
  { dim: 'Merchant', count: 8, examples: 'Intrinsic risk, age, chargeback rate, CNP share' },
  { dim: 'Temporal', count: 6, examples: 'Hour, weekday, night/weekend, hour deviation' },
  { dim: 'Account/Identity', count: 6, examples: 'Account age, KYC level, identity-doc score' },
  { dim: 'Session/Auth', count: 12, examples: 'Failed logins, beneficiary age, VPN hosting' },
  { dim: 'Methods/Channels', count: 12, examples: 'One-hot payment method, channel, type' },
  { dim: 'Sequence/Graph', count: 4, examples: 'Stage index, risk events (24h), beneficiary in-degree' }
];

let yPos = 1.7;
featureDims.forEach(f => {
  slide.addShape(pres.ShapeType.rectangle, {
    x: 0.5, y: yPos, w: 1.8, h: 0.32,
    fill: { color: colors.primary },
    line: { type: 'none' }
  });
  
  slide.addText(f.dim, {
    x: 0.6, y: yPos + 0.04, w: 1.6, h: 0.24,
    fontSize: 11, bold: true, color: colors.white, isTextBox: true
  });
  
  slide.addShape(pres.ShapeType.rectangle, {
    x: 2.4, y: yPos, w: 0.5, h: 0.32,
    fill: { color: colors.secondary },
    line: { type: 'none' }
  });
  
  slide.addText(f.count.toString(), {
    x: 2.4, y: yPos + 0.04, w: 0.5, h: 0.24,
    fontSize: 12, bold: true, color: colors.white, align: 'center', isTextBox: true
  });
  
  slide.addText(f.examples, {
    x: 3.0, y: yPos + 0.04, w: 6.5, h: 0.24,
    fontSize: 10, color: colors.darkText, isTextBox: true
  });
  
  yPos += 0.38;
});

// ===== SLIDE 14: ML CORE =====
slide = addContentSlide(pres, 'ML Core: From-Scratch Histogram GBDT & Random Forest');

slide.addText('Verified Against Theoretical Bounds', {
  x: 0.5, y: 1.2, w: 9, h: 0.3,
  fontSize: 18, bold: true, color: colors.dark, isTextBox: true
});

slide.addShape(pres.ShapeType.rectangle, {
  x: 0.5, y: 1.7, w: 4.4, h: 1.3,
  fill: { color: colors.light },
  line: { color: colors.primary, width: 2 }
});

slide.addText('GBDT Achievement', {
  x: 0.7, y: 1.8, w: 4.0, h: 0.25,
  fontSize: 14, bold: true, color: colors.primary, isTextBox: true
});

slide.addText(
  'Bayes-Optimal AUC: 0.8969\n' +
  'Our GBDT AUC: 0.8842\n' +
  '= 98.6% of theoretical max',
  {
    x: 0.7, y: 2.15, w: 4.0, h: 0.7,
    fontSize: 13, color: colors.darkText, align: 'center', isTextBox: true
  }
);

slide.addShape(pres.ShapeType.rectangle, {
  x: 5.1, y: 1.7, w: 4.4, h: 1.3,
  fill: { color: colors.light },
  line: { color: colors.secondary, width: 2 }
});

slide.addText('TreeSHAP Verification', {
  x: 5.3, y: 1.8, w: 4.0, h: 0.25,
  fontSize: 14, bold: true, color: colors.secondary, isTextBox: true
});

slide.addText(
  'vs Brute-Force Shapley:\n' +
  '2.7e-08 absolute error\n' +
  'Flat across depths 2–6',
  {
    x: 5.3, y: 2.15, w: 4.0, h: 0.7,
    fontSize: 13, color: colors.darkText, align: 'center', isTextBox: true
  }
);

slide.addText('Model Specifications', {
  x: 0.5, y: 3.2, w: 9, h: 0.3,
  fontSize: 16, bold: true, color: colors.accent, isTextBox: true
});

slide.addText(
  'GBDT: 300 trees, 64 histogram bins, max depth 6, max leaves 63, early stopping (30 rounds), logistic loss with Hessians\n' +
  'RF: 120 trees, max depth 14, class-weight balanced, Gini splitting (equivalent to squared-error on 0/1)',
  {
    x: 0.7, y: 3.65, w: 8.6, h: 0.7,
    fontSize: 12, color: colors.darkText, isTextBox: true
  }
);

// ===== SLIDE 15: EXPLAINABILITY =====
slide = addContentSlide(pres, 'Explainability: Path-Dependent TreeSHAP');

slide.addText('Every Decision is Attributable', {
  x: 0.5, y: 1.2, w: 9, h: 0.3,
  fontSize: 18, bold: true, color: colors.dark, isTextBox: true
});

slide.addShape(pres.ShapeType.rectangle, {
  x: 0.5, y: 1.7, w: 9, h: 1.6,
  fill: { color: colors.light },
  line: { color: colors.primary, width: 2 }
});

slide.addText('Per-Transaction Output', {
  x: 0.7, y: 1.8, w: 8.6, h: 0.25,
  fontSize: 14, bold: true, color: colors.primary, isTextBox: true
});

slide.addText(
  '✓ Base value & feature contributions (risk-increasing vs protective)\n' +
  '✓ Risk score (0–100) & risk band (LOW / MEDIUM / HIGH / CRITICAL)\n' +
  '✓ Recommended action (ALLOW / MONITOR / STEP_UP_AUTH / HOLD_REVIEW)\n' +
  '✓ Human-readable narrative: "New beneficiary (+31%), Velocity anomaly (+22%), Amount deviation (+19%)"\n' +
  '✓ Interactive waterfall chart in dashboard (red = risk up, teal = risk down)',
  {
    x: 0.7, y: 2.1, w: 8.6, h: 1.1,
    fontSize: 11, color: colors.darkText, isTextBox: true
  }
);

slide.addText('Risk Band Policy (Tunable Prototype Thresholds)', {
  x: 0.5, y: 3.6, w: 9, h: 0.3,
  fontSize: 16, bold: true, color: colors.accent, isTextBox: true
});

const riskBands = [
  { band: 'LOW (0–30)', action: 'ALLOW — no friction' },
  { band: 'MEDIUM (30–60)', action: 'MONITOR — approve, log for review' },
  { band: 'HIGH (60–80)', action: 'STEP_UP_AUTH — challenge before settlement' },
  { band: 'CRITICAL (80–100)', action: 'HOLD_REVIEW — fraud analyst queue' }
];

let yPos = 4.0;
riskBands.forEach(rb => {
  slide.addShape(pres.ShapeType.rectangle, {
    x: 0.5, y: yPos, w: 1.8, h: 0.3,
    fill: { color: colors.secondary },
    line: { type: 'none' }
  });
  
  slide.addText(rb.band, {
    x: 0.6, y: yPos + 0.04, w: 1.6, h: 0.22,
    fontSize: 11, bold: true, color: colors.white, isTextBox: true
  });
  
  slide.addText(rb.action, {
    x: 2.4, y: yPos + 0.04, w: 7.1, h: 0.22,
    fontSize: 11, color: colors.darkText, isTextBox: true
  });
  
  yPos += 0.35;
});

// ===== SLIDE 16: GAP ANALYSIS =====
slide = addContentSlide(pres, 'Gap Analysis: 10 Evasion Hypotheses Ranked by Lift');

slide.addText('When attacks evade, the system ranks structural weaknesses to prioritize improvement.', {
  x: 0.5, y: 1.2, w: 9, h: 0.3,
  fontSize: 14, color: colors.gray, isTextBox: true
});

const hypotheses = [
  'Low Value — amounts 2–3× customer median vs attack at 1.5×',
  'Slow Pacing — 1 txn per 12h vs rapid sequences',
  'Familiar Device — reuse primary device, is_new_device=0',
  'Familiar Geography — attacks from home city or frequent location',
  'Existing Payee — reuse known beneficiary',
  'Merchant Mimicry — use merchants customer frequents',
  'No Credential Trace — avoid password/profile changes',
  'Low Velocity Footprint — single drain not rapid multi-step',
  'Thin But Clean Identity — synthetic ID built to mimic honest customer',
  'Sequence Only — visible only as ordered sequence, not single row'
];

let yPos = 1.8;
hypotheses.forEach((h, idx) => {
  const colors_list = [colors.primary, colors.secondary, colors.accent, colors.warning];
  const color = colors_list[idx % 4];
  
  slide.addShape(pres.ShapeType.rectangle, {
    x: 0.5, y: yPos, w: 0.3, h: 0.28,
    fill: { color: color },
    line: { type: 'none' }
  });
  
  slide.addText((idx + 1) + '.', {
    x: 0.95, y: yPos + 0.03, w: 0.5, h: 0.22,
    fontSize: 11, bold: true, color: colors.darkText, isTextBox: true
  });
  
  slide.addText(h, {
    x: 1.6, y: yPos + 0.03, w: 7.9, h: 0.22,
    fontSize: 10, color: colors.darkText, isTextBox: true
  });
  
  yPos += 0.33;
});

// ===== SLIDE 17: ADAPTIVE LOOP =====
slide = addContentSlide(pres, 'Adaptive Loop: Anti-Cheat by Construction');

slide.addText('Dual-Batch Design Prevents Overfitting', {
  x: 0.5, y: 1.2, w: 9, h: 0.3,
  fontSize: 18, bold: true, color: colors.dark, isTextBox: true
});

const steps = [
  { num: '1', title: 'Identify Weakness', desc: 'Gap analysis ranks evasion hypotheses' },
  { num: '2', title: 'Generate Adversarial', desc: 'Red Team creates two independent batches (adv_train, adv_eval)' },
  { num: '3', title: 'Retrain', desc: 'Only adv_train touches the model (never adv_eval)' },
  { num: '4', title: 'Evaluate', desc: 'Report numbers on adv_eval (never seen during training)' },
  { num: '5', title: 'Regression Check', desc: 'Measure impact on original attack distribution' }
];

let yPos = 1.8;
steps.forEach(s => {
  slide.addShape(pres.ShapeType.circle, {
    x: 0.5, y: yPos, w: 0.4, h: 0.4,
    fill: { color: colors.primary },
    line: { type: 'none' }
  });
  
  slide.addText(s.num, {
    x: 0.5, y: yPos, w: 0.4, h: 0.4,
    fontSize: 18, bold: true, color: colors.white, align: 'center', valign: 'middle', isTextBox: true
  });
  
  slide.addText(s.title, {
    x: 1.1, y: yPos + 0.05, w: 1.5, h: 0.3,
    fontSize: 12, bold: true, color: colors.primary, isTextBox: true
  });
  
  slide.addText(s.desc, {
    x: 2.7, y: yPos + 0.05, w: 6.8, h: 0.3,
    fontSize: 11, color: colors.gray, isTextBox: true
  });
  
  yPos += 0.5;
});

slide.addText('Matched FPR: Threshold always chosen on validation to maintain constant false-positive budget (default 1%).', {
  x: 0.5, y: 4.3, w: 9, h: 0.35,
  fontSize: 12, italic: true, color: colors.accent, isTextBox: true
});

slide.addText('No threshold lowering allowed — gains must reflect genuine model strength, not operating point shift.', {
  x: 0.5, y: 4.7, w: 9, h: 0.3,
  fontSize: 12, italic: true, color: colors.accent, isTextBox: true
});

// ===== SLIDE 18: SYSTEM ARCHITECTURE =====
slide = addContentSlide(pres, '8. Developed Prototype: System Architecture');

slide.addText('Two-Process Lab', {
  x: 0.5, y: 1.2, w: 9, h: 0.3,
  fontSize: 18, bold: true, color: colors.dark, isTextBox: true
});

slide.addShape(pres.ShapeType.rectangle, {
  x: 0.5, y: 1.7, w: 4.3, h: 1.3,
  fill: { color: colors.light },
  line: { color: colors.primary, width: 2 }
});

slide.addText('Python Core (~7.8k LOC)', {
  x: 0.7, y: 1.8, w: 3.9, h: 0.25,
  fontSize: 13, bold: true, color: colors.primary, isTextBox: true
});

slide.addText(
  '✓ Synthetic data engine\n' +
  '✓ Red Team + Blue Team ML\n' +
  '✓ Feature engineering (83)\n' +
  '✓ Risk scoring & explainability\n' +
  '✓ Gap analysis & adaptive loop\n' +
  '✓ SQLite store\n' +
  '✓ REST API + SSE\n' +
  '✓ Snapshot persistence',
  {
    x: 0.7, y: 2.15, w: 3.9, h: 0.8,
    fontSize: 10, color: colors.darkText, isTextBox: true
  }
);

slide.addShape(pres.ShapeType.rectangle, {
  x: 5.2, y: 1.7, w: 4.3, h: 1.3,
  fill: { color: colors.light },
  line: { color: colors.secondary, width: 2 }
});

slide.addText('Next.js 14 Dashboard', {
  x: 5.4, y: 1.8, w: 3.9, h: 0.25,
  fontSize: 13, bold: true, color: colors.secondary, isTextBox: true
});

slide.addText(
  '✓ 9 views: Overview, Studio,\n' +
  '  Red Team, Blue Team,\n' +
  '  Explainability, Live, Intelligence,\n' +
  '  Gap Analysis, Adaptive Loop\n' +
  '✓ SSE client (real-time updates)\n' +
  '✓ Interactive charts\n' +
  '✓ Responsive dark theme\n' +
  '✓ Mobile/tablet/desktop',
  {
    x: 5.4, y: 2.15, w: 3.9, h: 0.8,
    fontSize: 10, color: colors.darkText, isTextBox: true
  }
);

slide.addText('Runtime Topology', {
  x: 0.5, y: 3.2, w: 9, h: 0.3,
  fontSize: 16, bold: true, color: colors.primary, isTextBox: true
});

slide.addText('Browser → Next.js (:3000) → Python API (:8000) ← → AppState (in-memory) ← → Store (SQLite) ← → Snapshots', {
  x: 0.7, y: 3.6, w: 8.6, h: 0.3,
  fontSize: 12, color: colors.darkText, isTextBox: true
});

slide.addText('Async Patterns', {
  x: 0.5, y: 4.1, w: 9, h: 0.3,
  fontSize: 16, bold: true, color: colors.accent, isTextBox: true
});

slide.addText(
  'Heavy operations (simulate, red-team generate, loop) → async jobs (202 Created + job ID) → SSE stream (generation/progress/done events)\n' +
  'Fast reboot: snapshot loads in ~seconds (world pickle + detector JSON), pre-warms cache',
  {
    x: 0.7, y: 4.45, w: 8.6, h: 0.5,
    fontSize: 12, color: colors.darkText, isTextBox: true
  }
);

// ===== SLIDE 19: SCALABLE ARCHITECTURE =====
slide = addContentSlide(pres, '9. Scalable System Architecture (Target Design)');

slide.addText('Path from Single-Node to Enterprise Scale', {
  x: 0.5, y: 1.2, w: 9, h: 0.3,
  fontSize: 16, bold: true, color: colors.primary, isTextBox: true
});

slide.addShape(pres.ShapeType.rectangle, {
  x: 0.5, y: 1.7, w: 9, h: 0.8,
  fill: { color: colors.light },
  line: { color: colors.primary, width: 1 }
});

slide.addText('Scale-Out Components', {
  x: 0.7, y: 1.75, w: 8.6, h: 0.2,
  fontSize: 13, bold: true, color: colors.primary, isTextBox: true
});

slide.addText(
  'Load Balancer/API Gateway | Stateless Web Tier (Next.js) | Stateless API Tier (FastAPI) | Job Queue (Redis/RabbitMQ) | ' +
  'Worker Pool (Generation/Feature/Training) | PostgreSQL (partitioned) | Object Storage (snapshots, CSVs, models) | Model Registry',
  {
    x: 0.7, y: 2.0, w: 8.6, h: 0.5,
    fontSize: 11, color: colors.darkText, isTextBox: true
  }
);

slide.addText('Design Qualities', {
  x: 0.5, y: 2.65, w: 9, h: 0.3,
  fontSize: 16, bold: true, color: colors.accent, isTextBox: true
});

const qualities = [
  { qual: 'Feasibility', desc: 'Core runs on numpy+pandas only; every piece maps to existing code' },
  { qual: 'Maintainability', desc: 'Single source of truth per concern (config, schema, taxonomy); assertions everywhere' },
  { qual: 'Scalability', desc: 'Stateless tiers scale horizontally; embarrassingly parallel batch work (by customer_id)' },
  { qual: 'Availability', desc: 'Multi-replica stateless tiers + queue durability + snapshot restore' },
  { qual: 'Performance', desc: 'Histogram binning bounds training; snapshot boot removes cold-start; memoization' },
  { qual: 'Cost', desc: 'CPU-friendly (no GPU required); burst work spread over idle workers' }
];

let yPos = 3.1;
qualities.forEach(q => {
  slide.addText(q.qual + ':', {
    x: 0.7, y: yPos, w: 2.0, h: 0.25,
    fontSize: 12, bold: true, color: colors.primary, isTextBox: true
  });
  slide.addText(q.desc, {
    x: 2.8, y: yPos, w: 6.5, h: 0.25,
    fontSize: 11, color: colors.darkText, isTextBox: true
  });
  yPos += 0.32;
});

// ===== SLIDE 20: DATA FLOW DIAGRAM =====
slide = addContentSlide(pres, '10. Data Flow Diagram (Current)');

slide.addText('End-to-End: From Generation to Dashboard', {
  x: 0.5, y: 1.2, w: 9, h: 0.3,
  fontSize: 16, bold: true, color: colors.primary, isTextBox: true
});

// Simplified ASCII art version
slide.addText(
  'SOURCES (attack_taxonomy.json, config.py, SEED)\n' +
  '    ↓\n' +
  'build_world() → merge legit + attack events\n' +
  '    ↓\n' +
  'build_features() → 83 causal features (STRICT causality)\n' +
  '    ↓\n' +
  'SPLIT (temporal, campaign-grouped)\n' +
  'train / validation / test\n' +
  '    ↓\n' +
  'TRAIN GBDT/RF → threshold at FPR budget\n' +
  '    ↓\n' +
  'SCORE + TreeSHAP → risk band + reason codes\n' +
  '    ↓\n' +
  'GAP ANALYSIS (10 hypotheses, ranked by lift)\n' +
  '    ↓\n' +
  'ADVERSARIAL GENERATOR (dual batches: train & eval)\n' +
  '    ↓\n' +
  'RETRAIN + RETEST (matched FPR, regression check)\n' +
  '    ↓\n' +
  'STORE (SQLite) + ARTEFACTS (experiments/results/) + DASHBOARD',
  {
    x: 0.7, y: 1.7, w: 8.6, h: 3.5,
    fontSize: 10, color: colors.darkText, fontFace: 'Courier New', isTextBox: true
  }
);

// ===== SLIDE 21: ML ARCHITECTURE - DATA COLLECTION =====
slide = addContentSlide(pres, '11. ML Architecture: Data Collection Pipeline');

slide.addText('From Raw Events to Feature Matrix', {
  x: 0.5, y: 1.2, w: 9, h: 0.3,
  fontSize: 16, bold: true, color: colors.primary, isTextBox: true
});

const pipeline_stages = [
  { stage: '1. Synthesis', desc: 'Generate synthetic population (personas, merchants, devices, cities)' },
  { stage: '2. Transactions', desc: 'Legitimate traffic with realistic hour curves, life events (~98.4% approved)' },
  { stage: '3. Attack Injection', desc: 'Splice attack sequences into victim timelines (earned features, not stamped)' },
  { stage: '4. Event Stream', desc: 'Merge & sort by (timestamp, txn_id); 26 event columns' },
  { stage: '5. Feature Eng', desc: 'Streaming pass (append AFTER emitting) → 83 features, STRICT causality' },
  { stage: '6. Guardrails', desc: 'Assert no label column is feature; single-feature AUC ≤ 0.99; bit-identical under truncation' }
];

let yPos = 1.8;
pipeline_stages.forEach((ps, idx) => {
  slide.addShape(pres.ShapeType.rectangle, {
    x: 0.5, y: yPos, w: 1.2, h: 0.35,
    fill: { color: colors.primary },
    line: { type: 'none' }
  });
  
  slide.addText(ps.stage, {
    x: 0.6, y: yPos + 0.05, w: 1.0, h: 0.25,
    fontSize: 11, bold: true, color: colors.white, isTextBox: true
  });
  
  slide.addText(ps.desc, {
    x: 1.8, y: yPos + 0.05, w: 7.7, h: 0.25,
    fontSize: 11, color: colors.darkText, isTextBox: true
  });
  
  yPos += 0.4;
});

// ===== SLIDE 22: ML ARCHITECTURE - TRAINING =====
slide = addContentSlide(pres, 'ML Architecture: Training Pipeline');

slide.addText('From Feature Matrix to Trained Detector', {
  x: 0.5, y: 1.2, w: 9, h: 0.3,
  fontSize: 16, bold: true, color: colors.primary, isTextBox: true
});

const training_stages = [
  { stage: 'Feature Matrix', desc: 'X (n × 83) + y (fraud_label) + campaign metadata' },
  { stage: 'Temporal Split', desc: 'Earliest window → train; validation/test are later (no time leakage)' },
  { stage: 'Campaign Guard', desc: 'Every attack_id entirely in one fold (no campaign leakage)' },
  { stage: 'Threshold Policy', desc: 'Choose highest-recall threshold whose FPR on legit ≤ budget (default 1%)' },
  { stage: 'Training', desc: 'Histogram GBDT (300 trees) + Random Forest (120 trees); logistic loss, Gini splits' },
  { stage: 'Evaluation', desc: 'ROC-AUC, PR-AUC, recall at threshold, bootstrap CIs, recall by segment' },
  { stage: 'Explainability', desc: 'TreeSHAP (verified 2.7e-08 vs Shapley); reason codes; risk bands' },
  { stage: 'Gap Analysis', desc: '10 hypotheses × (share_of_missed, lift) → attribution ranking' }
];

let yPos = 1.8;
training_stages.forEach((ts, idx) => {
  const colors_list = [colors.primary, colors.primary, colors.secondary, colors.secondary, colors.accent, colors.accent, colors.warning, colors.warning];
  const color = colors_list[idx];
  
  slide.addShape(pres.ShapeType.rectangle, {
    x: 0.5, y: yPos, w: 1.4, h: 0.3,
    fill: { color: color },
    line: { type: 'none' }
  });
  
  slide.addText(ts.stage, {
    x: 0.6, y: yPos + 0.04, w: 1.2, h: 0.22,
    fontSize: 10, bold: true, color: colors.white, isTextBox: true
  });
  
  slide.addText(ts.desc, {
    x: 1.95, y: yPos + 0.04, w: 7.55, h: 0.22,
    fontSize: 10, color: colors.darkText, isTextBox: true
  });
  
  yPos += 0.35;
});

// ===== SLIDE 23: ML ARCHITECTURE - REAL-TIME =====
slide = addContentSlide(pres, 'ML Architecture: Real-Time Implementation');

slide.addText('From Trained Model to Production Inference', {
  x: 0.5, y: 1.2, w: 9, h: 0.3,
  fontSize: 16, bold: true, color: colors.primary, isTextBox: true
});

slide.addShape(pres.ShapeType.rectangle, {
  x: 0.5, y: 1.7, w: 9, h: 2.3,
  fill: { color: colors.light },
  line: { color: colors.primary, width: 2 }
});

slide.addText('Live Transaction', {
  x: 0.7, y: 1.8, w: 8.6, h: 0.25,
  fontSize: 13, bold: true, color: colors.primary, isTextBox: true
});

slide.addText(
  '↓ (customer_id, merchant_id, amount, device, location, timestamp, ...)\n' +
  '↓\n' +
  'Feature Builder (lookup customer/merchant history, compute 83 features) → microseconds\n' +
  '↓\n' +
  'Model Inference (GBDT 300 trees + RF 120 trees) → microseconds\n' +
  '↓\n' +
  'Risk Scoring (probability → score 0–100 → band)\n' +
  '↓\n' +
  'TreeSHAP Explanation (reason codes + waterfall) → microseconds\n' +
  '↓\n' +
  'Decision (ALLOW / MONITOR / STEP_UP_AUTH / HOLD_REVIEW)\n' +
  '↓\n' +
  'Action (approve, log, challenge, block)\n' +
  '↓\n' +
  'Feedback Loop (capture fraud labels → drift detection → retrain schedule)',
  {
    x: 0.7, y: 2.1, w: 8.6, h: 1.8,
    fontSize: 10, color: colors.darkText, fontFace: 'Courier New', isTextBox: true
  }
);

slide.addText('Latency Budget: <5ms per transaction (achievable with tree model serving behind model registry)', {
  x: 0.5, y: 4.2, w: 9, h: 0.4,
  fontSize: 12, italic: true, color: colors.accent, isTextBox: true
});

// ===== SLIDE 24: RESULTS & VERIFICATION =====
slide = addContentSlide(pres, '12. Results & Verification: All Green');

slide.addShape(pres.ShapeType.rectangle, {
  x: 0.5, y: 1.2, w: 4.4, h: 1.8,
  fill: { color: colors.light },
  line: { color: colors.success, width: 2 }
});

slide.addText('Unit Tests', {
  x: 0.7, y: 1.3, w: 4.0, h: 0.25,
  fontSize: 13, bold: true, color: colors.success, isTextBox: true
});

slide.addText('92 / 92 passing\n~56 seconds\n\nCausality, leakage, metrics, ML correctness, API contracts all verified', {
  x: 0.7, y: 1.65, w: 4.0, h: 1.2,
  fontSize: 11, color: colors.darkText, align: 'center', isTextBox: true
});

slide.addShape(pres.ShapeType.rectangle, {
  x: 5.1, y: 1.2, w: 4.4, h: 1.8,
  fill: { color: colors.light },
  line: { color: colors.success, width: 2 }
});

slide.addText('End-to-End Verification', {
  x: 5.3, y: 1.3, w: 4.0, h: 0.25,
  fontSize: 13, bold: true, color: colors.success, isTextBox: true
});

slide.addText('14 / 14 stages passing\n~90 seconds (quick)\n\n14 asserting stages verify correctness throughout pipeline', {
  x: 5.3, y: 1.65, w: 4.0, h: 1.2,
  fontSize: 11, color: colors.darkText, align: 'center', isTextBox: true
});

slide.addShape(pres.ShapeType.rectangle, {
  x: 0.5, y: 3.3, w: 4.4, h: 1.4,
  fill: { color: colors.light },
  line: { color: colors.success, width: 2 }
});

slide.addText('Frontend Build', {
  x: 0.7, y: 3.4, w: 4.0, h: 0.25,
  fontSize: 13, bold: true, color: colors.success, isTextBox: true
});

slide.addText('Clean production build\nZero console errors\nResponsive at all widths', {
  x: 0.7, y: 3.75, w: 4.0, h: 0.85,
  fontSize: 11, color: colors.darkText, align: 'center', isTextBox: true
});

slide.addShape(pres.ShapeType.rectangle, {
  x: 5.1, y: 3.3, w: 4.4, h: 1.4,
  fill: { color: colors.light },
  line: { color: colors.success, width: 2 }
});

slide.addText('Correctness Proofs', {
  x: 5.3, y: 3.4, w: 4.0, h: 0.25,
  fontSize: 13, bold: true, color: colors.success, isTextBox: true
});

slide.addText('GBDT: 98.6% of theory\nTreeSHAP: 2.7e-08 vs Shapley\nCausality: bit-identical truncation', {
  x: 5.3, y: 3.75, w: 4.0, h: 0.85,
  fontSize: 11, color: colors.darkText, align: 'center', isTextBox: true
});

// ===== SLIDE 25: CHALLENGES =====
slide = addContentSlide(pres, '13. Challenges We Faced & Solutions');

const challenges = [
  { ch: 'Air-Gapped Environment', sol: 'Built ML from scratch in numpy; verified correctness (98.6% AUC, 2.7e-08 TreeSHAP agreement)' },
  { ch: 'Label Leakage (3 found)', sol: 'Automated audit caught all; device reputation, registration event, footprint oracle—all fixed, regression-tested' },
  { ch: 'Causality Enforcement', sol: 'Structural: emit features before appending row; proved via truncation test (bit-identical)' },
  { ch: 'Campaign Leakage', sol: 'Temporal + campaign-grouped splits; every attack_id stays in one fold' },
  { ch: 'Baseline Regression', sol: 'Reported honestly (+13.5 on adv_eval, −11.1 on baseline); planned: mixed-ratio retraining' },
  { ch: 'FPR Disparity Across Personas', sol: 'Reported per-segment FPRs (0.46%–1.46%), not just aggregate' }
];

let yPos = 1.3;
challenges.forEach(c => {
  slide.addShape(pres.ShapeType.rectangle, {
    x: 0.5, y: yPos, w: 2.2, h: 0.3,
    fill: { color: colors.accent },
    line: { type: 'none' }
  });
  
  slide.addText(c.ch, {
    x: 0.6, y: yPos + 0.05, w: 2.0, h: 0.2,
    fontSize: 10, bold: true, color: colors.white, isTextBox: true
  });
  
  slide.addText(c.sol, {
    x: 2.8, y: yPos + 0.05, w: 6.7, h: 0.2,
    fontSize: 10, color: colors.darkText, isTextBox: true
  });
  
  yPos += 0.38;
});

// ===== SLIDE 26: FUTURE SCOPE =====
slide = addContentSlide(pres, 'Future Scope: 13 GenAI-Native Families & Beyond');

slide.addText('Near-Term (Next Sprint)', {
  x: 0.5, y: 1.2, w: 9, h: 0.3,
  fontSize: 16, bold: true, color: colors.primary, isTextBox: true
});

slide.addText(
  '→ Extend taxonomy from 7 to 13 families (GenAI-native: Deepfake ATO, Conversational Agent, Agentic APP, Deepfake KYC, Mule Network, Invoice-Timed BEC)\n' +
  '→ New event columns for GenAI signals (voice-verification authenticity, liveness confidence, agent-session anomaly)\n' +
  '→ Emergence experiment: train on classic, zero-shot evaluate on GenAI, then adaptive-loop improvement',
  {
    x: 0.7, y: 1.6, w: 8.6, h: 0.8,
    fontSize: 12, color: colors.darkText, isTextBox: true
  }
);

slide.addText('Medium-Term Product Roadmap', {
  x: 0.5, y: 2.6, w: 9, h: 0.3,
  fontSize: 16, bold: true, color: colors.secondary, isTextBox: true
});

slide.addText(
  '→ Mixed-ratio retraining (eliminate −11.1 pt baseline regression)\n' +
  '→ Sequence & graph models (score entire timeline, beneficiary networks)\n' +
  '→ Cost-sensitive thresholds (fraud loss vs false-positive cost)\n' +
  '→ Real-data calibration (compare synthetic ↔ real distributions)\n' +
  '→ Wider evasion search (LLM-based variant explorer)\n' +
  '→ Real-time streaming detector with continuous model versioning\n' +
  '→ Media-authenticity fusion (liveness + voice-verification)\n' +
  '→ Federated playbooks (share anonymized attack profiles across institutions)',
  {
    x: 0.7, y: 3.0, w: 8.6, h: 1.6,
    fontSize: 11, color: colors.darkText, isTextBox: true
  }
);

// ===== SLIDE 27: IMPACT & VISION =====
slide = addContentSlide(pres, 'Impact: Proactive Payment Security');

slide.addShape(pres.ShapeType.rectangle, {
  x: 0.5, y: 1.2, w: 9, h: 1.1,
  fill: { color: colors.light },
  line: { color: colors.accent, width: 3 }
});

slide.addText(
  'The Shift: From Reactive to Proactive\n' +
  'THEN: Train on yesterday\'s fraud → deploy → detect when real customers get attacked\n' +
  'NOW: Simulate tomorrow\'s fraud → find weaknesses today → prove improvements → deploy with confidence',
  {
    x: 0.7, y: 1.3, w: 8.6, h: 0.95,
    fontSize: 13, bold: true, color: colors.accent, align: 'center', isTextBox: true
  }
);

slide.addText('Key Achievements', {
  x: 0.5, y: 2.5, w: 9, h: 0.3,
  fontSize: 16, bold: true, color: colors.primary, isTextBox: true
});

const achievements = [
  '✓ Fully working MVP: 92 tests, 14 verification stages, clean build',
  '✓ Measured adaptive loop: +13.5 pts recall at matched FPR (with regression reported)',
  '✓ 83 strictly-causal features with structural causality guarantee',
  '✓ 7 parameterized attack families (extensible to 13)',
  '✓ TreeSHAP verified to mathematical definition (2.7e-08)',
  '✓ Zero real customer data needed — fully synthetic',
  '✓ Scalable design: single-node today, enterprise-ready architecture'
];

let yPos = 3.0;
achievements.forEach(a => {
  slide.addText(a, {
    x: 0.7, y: yPos, w: 8.6, h: 0.28,
    fontSize: 12, color: colors.darkText, isTextBox: true
  });
  yPos += 0.33;
});

// ===== SLIDE 28: CLOSING SLIDE =====
slide = addTitleSlide(pres, 'SovereignGuard', 'Don\'t wait for criminals to test your fraud system.\nTest it yourself first.', colors.dark);

slide.addText('• Continuous Adversarial Stress-Testing Lab\n• Proactive Payment Security\n• AI Red Team vs AI Blue Team\n• Proven by Measured Results', {
  x: 1.0, y: 4.0, w: 8, h: 0.8,
  fontSize: 16, color: colors.light, align: 'center', isTextBox: true
});

// Save the presentation
pres.writeFile({ fileName: '/mnt/user-data/outputs/SovereignGuard_Presentation.pptx' });
console.log('✅ Presentation created successfully!');
console.log('📊 File: /mnt/user-data/outputs/SovereignGuard_Presentation.pptx');
console.log('📌 Total Slides: 28');
console.log('\n🎯 Coverage:');
console.log('  1. Ideation & Problem Statement');
console.log('  2. Market Reality Numbers');
console.log('  3. Solution Proposed');
console.log('  4. Hero Loop (IDENTIFY→GENERATE→ATTACK→DETECT→EXPLAIN→ADAPT→RETEST)');
console.log('  5. Headline Results (+13.5 pts at matched FPR)');
console.log('  6. Solution Features vs Existing');
console.log('  7. Unique Technology Stack');
console.log('  8. Attack Family Segregation (7→13)');
console.log('  9. Synthetic Data Generation');
console.log('  10. Attack Injection Strategy');
console.log('  11. Scale Profiles');
console.log('  12. 83 Causal Features');
console.log('  13. ML Core (GBDT 98.6%, TreeSHAP 2.7e-08)');
console.log('  14. Explainability & Risk Bands');
console.log('  15. Gap Analysis (10 Hypotheses)');
console.log('  16. Adaptive Loop (Anti-Cheat Design)');
console.log('  17. System Architecture');
console.log('  18. Scalable Architecture');
console.log('  19. Data Flow Diagram');
console.log('  20. ML Architecture - Data Collection');
console.log('  21. ML Architecture - Training');
console.log('  22. ML Architecture - Real-Time');
console.log('  23. Results & Verification');
console.log('  24. Challenges Faced & Solutions');
console.log('  25. Future Scope');
console.log('  26. Impact & Vision');
console.log('  27. Closing Slide');
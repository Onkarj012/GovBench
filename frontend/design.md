# IRBG Frontend — Design Specification

Design system extracted from the two DeepSWE reference captures
(`references/DeepSWE (5_30_2026 12：38：41 AM).html` = homepage `/`,
`references/DeepSWE (5_30_2026 12：39：56 AM).html` = blog `/blog`) and adapted
for the IRBG (Institutional Readiness & Bias Benchmark for Governance) frontend.

The reference is a **Next.js + Tailwind CSS v4** benchmark site by Datacurve. It
is dark-first, minimal, monochrome-with-accents, and data-dense. This document
captures every design token and pattern so the IRBG UI can match it.

---

## 1. Design Principles

- **Dark-first, monochrome base.** Near-black canvas, slightly lighter cards, white text. Color is reserved for data (scores, model families, languages, pass/fail).
- **Minimal chrome.** Thin 1px borders, no heavy shadows, no gradients in the reference (gradients are an IRBG addition for score bars).
- **Data density over decoration.** Tight tables, compact bars, monospace numerics.
- **Typography-led hierarchy.** Weight + size + tracking do the work; few dividers.
- **Restrained motion.** Only `transition-colors` / `transition-all` at `0.15s`; one `pulse` keyframe.

---

## 2. Color System

The reference defines **two themes** via CSS custom properties: light (`:root`)
and dark (`.dark`). Colors use the **OKLCH** color space. The site ships
`class="dark"` on `<html>`, so the dark values are the defaults we target.

### 2.1 Core surface & text tokens

| Token | Light (`:root`) | Dark (`.dark`) — **our target** | Role |
|---|---|---|---|
| `--background` | `oklch(100% 0 0)` (`#fff`) | `#151515` | Page canvas |
| `--foreground` | `oklch(14.5% 0 0)` | `oklch(98.5% 0 0)` (near-white) | Primary text |
| `--card` | `oklch(100% 0 0)` | `#1d1d1d` | Card / panel surface |
| `--card-foreground` | `oklch(14.5% 0 0)` | `oklch(98.5% 0 0)` | Text on cards |
| `--popover` | `#fff` | `#1d1d1d` | Popover surface |
| `--muted` | `oklch(97% 0 0)` | `#232323` | Subtle fill |
| `--muted-foreground` | `oklch(55.6% 0 0)` | `oklch(72% 0 0)` | Secondary / dim text |
| `--accent` | `oklch(97% 0 0)` | `#232323` | Hover fill |
| `--accent-foreground` | `oklch(20.5% 0 0)` | `oklch(98.5% 0 0)` | Text on accent |
| `--secondary` | `oklch(97% 0 0)` | `#232323` | Secondary button fill |
| `--primary` | `oklch(14.5% 0 0)` | `oklch(98.5% 0 0)` | Primary action (inverts) |
| `--primary-foreground` | `oklch(98.5% 0 0)` | `#151515` | Text on primary |
| `--border` | `oklch(92.2% 0 0)` | `#2a2a2a` | All 1px borders |
| `--input` | `oklch(92.2% 0 0)` | `#2a2a2a` | Input borders |
| `--ring` | `oklch(70.8% 0 0)` | `oklch(50% 0 0)` | Focus ring |
| `--color-black` | `#000` | `#000` | — |
| `--color-white` | `#fff` | `#fff` | — |

Note the **primary inversion**: in dark mode the primary button is near-white
with dark text (`Read the blog` CTA = `bg-foreground text-background`).

### 2.2 Semantic data colors

| Token | Light | Dark | Role |
|---|---|---|---|
| `--pass` | `oklch(55% .13 155)` | `oklch(72% .16 155)` | Pass / success (green) |
| `--fail` | `oklch(55% .17 27)` | `oklch(70% .19 27)` | Fail / error (red) |

For IRBG, map grades onto this same green→red hue axis:
**A** green `155` · **B** blue `250` · **C** yellow `95` · **D** orange `50` · **F** red `27`.

### 2.3 Model-family accent colors (`--family-*`)

Each AI vendor has a dedicated hue, used to tint leaderboard bars and badges.
Format: `oklch(L% C H)` — light theme then dark theme.

| Family | Light | Dark | Hue |
|---|---|---|---|
| anthropic | `oklch(62% .15 50)` | `oklch(78% .14 50)` | orange |
| openai | `oklch(58% .13 155)` | `oklch(75% .14 155)` | green |
| google | `oklch(58% .17 255)` | `oklch(74% .16 255)` | blue |
| deepseek | `oklch(55% .18 295)` | `oklch(72% .17 295)` | violet |
| moonshot | `oklch(60% .18 20)` | `oklch(74% .17 20)` | red |
| zhipu | `oklch(62% .12 195)` | `oklch(78% .12 195)` | teal |
| alibaba | `oklch(60% .15 220)` | `oklch(76% .14 220)` | cyan-blue |
| minimax | `oklch(62% .17 330)` | `oklch(76% .16 330)` | magenta |
| mistral | `oklch(62% .16 75)` | `oklch(78% .15 75)` | amber |
| xai | `oklch(56% .08 265)` | `oklch(74% .08 265)` | desat. blue |
| xiaomi | `oklch(65% .13 95)` | `oklch(80% .13 95)` | yellow-green |
| cursor | `oklch(56% .03 250)` | `oklch(76% .03 250)` | near-gray |
| other | `oklch(55% .02 270)` | `oklch(75% .02 270)` | gray |

**IRBG mapping:** `deepseek-v3`, `deepseek-v4-flash` → deepseek violet;
`claude-sonnet-4.6` → anthropic orange; `gemini-3.1-flash-lite` → google blue;
`gpt-oss-120b` → openai green; `kimi-k2.6` → moonshot red; `glm-4.7-flash` → zhipu teal.

### 2.4 Language colors (`--lang-*`) — for task/scenario tags

| Lang | Dark | Lang | Dark |
|---|---|---|---|
| typescript | `oklch(74% .16 250)` | python | `oklch(80% .13 95)` |
| javascript | `oklch(78% .14 60)` | rust | `oklch(74% .17 25)` |
| go | `oklch(78% .12 200)` | other | `oklch(75% .02 270)` |
| ink (label text on chip) | `oklch(98.5% 0 0)` | | |

---

## 3. Typography

### 3.1 Font families

| Token | Stack |
|---|---|
| `--font-sans` (default) | `ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol", "Noto Color Emoji", sans-serif` |
| `--font-mono` | `"Google Sans Code", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace` |

`--default-font-family: var(--font-sans)`, `--default-mono-font-family: var(--font-mono)`.
Mono is used for **all numerics** (scores, percents, token counts, latencies) and code.

> IRBG note: our scaffold uses Geist/Geist Mono. Either keep Geist or switch to
> the reference system stack + "Google Sans Code"; the rest of the spec is font-agnostic.

### 3.2 Type scale (Tailwind v4 tokens)

| Token | Size | Line-height |
|---|---|---|
| `--text-xs` | `0.75rem` (12px) | `calc(1 / 0.75)` ≈ 1.333 |
| `--text-sm` | `0.875rem` (14px) | `calc(1.25 / 0.875)` ≈ 1.429 |
| `--text-base` | `1rem` (16px) | `1.5` |
| `--text-lg` | `1.125rem` (18px) | `calc(1.75 / 1.125)` ≈ 1.556 |
| `--text-xl` | `1.25rem` (20px) | `calc(1.75 / 1.25)` = 1.4 |

Larger hero sizes come from Tailwind utilities (`text-4xl`/`text-5xl`).

### 3.3 Weights

| Token | Value |
|---|---|
| `--font-weight-normal` | 400 |
| `--font-weight-medium` | 500 |
| `--font-weight-semibold` | 600 |

No 700+ in the reference; the wordmark and headings use **600 (semibold)**.

### 3.4 Letter-spacing & leading

| Tracking | Value | | Leading | Value |
|---|---|---|---|---|
| `--tracking-tight` | `-0.025em` | | `--leading-tight` | 1.25 |
| `--tracking-normal` | `0em` | | `--leading-snug` | 1.375 |
| `--tracking-wide` | `0.025em` | | `--leading-relaxed` | 1.625 |
| `--tracking-wider` | `0.05em` | | | |

Wordmark uses a custom `tracking-[-0.02em]` with `leading-none`.
Headings use `tracking-tight`; uppercase labels use `tracking-wider`.

---

## 4. Spacing, Radius, Motion

- **Spacing base:** `--spacing: 0.25rem` (4px). All `p-`, `m-`, `gap-` are multiples.
- **Containers:** `--container-sm: 24rem`, `--container-lg: 32rem`. Page content wraps in `max-w-6xl` (≈72rem) or `max-w-5xl`, always `mx-auto px-4`. Prose blocks cap at `max-w-[60ch]`.
- **Radius:** `rounded-md` on buttons/cards. Bars/chips can be square or pill.
- **Transitions:** `--default-transition-duration: 0.15s`, timing `cubic-bezier(.4,0,.2,1)`; `--ease-out: cubic-bezier(0,0,.2,1)`.
- **Animation:** `--animate-pulse: pulse 2s cubic-bezier(.4,0,.6,1) infinite` (loading states only).

---

## 5. Layout Structure

```
<html class="dark">
 <body>                              bg --background, text --foreground
   ┌─ Header (sticky)               border-b border-border bg-background
   │   wordmark (left) · nav (center) · GitHub + theme toggle (right)
   ├─ Main  max-w-6xl mx-auto px-4 py-8
   │   ├─ Hero
   │   ├─ Leaderboard section
   │   ├─ Task / Scenario examples grid
   │   └─ Blog / sections
   └─ Footer                        border-t border-border, copyright + canary
```

- Single top-level **6xl** column, centered, 16px gutters.
- Sections separated by vertical padding (`py-8`+), not heavy rules.
- Two-column splits use CSS grid (`grid-cols-*`) collapsing to one column on mobile (`sm:`/`lg:` prefixes).

---

## 6. Components

### 6.1 Header / Nav
- Container: `border-b border-border bg-background`, height ~`h-14`, flex row.
- **Wordmark:** `text-lg sm:text-[20px] font-semibold tracking-[-0.02em] leading-none text-foreground`.
- **Nav links:** `px-3 h-9 inline-flex items-center text-muted-foreground hover:text-foreground transition-colors`, active state via `data-[status=active]:text-foreground`.
- **GitHub link:** same + `gap-1.5` for icon.
- **Theme toggle:** icon button `inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium transition-all`.

Nav items on reference: `Blog · Run · Data · GitHub` + theme toggle.
**IRBG nav:** `Leaderboard · Pillars · Runs · GitHub` + theme toggle.

### 6.2 Hero
- `H1` wordmark/title (large, semibold, tracking-tight).
- Sub-line in `--muted-foreground`: e.g. reference *"Measuring frontier coding agents on original, long-horizon engineering tasks."*
- A small `by <vendor>` link: `mt-3 inline-flex items-center gap-2 text-foreground hover:text-foreground/80 transition-colors`.
- **Primary CTA** (`Read the blog`): `inline-flex items-center gap-1.5 bg-foreground text-background px-4 h-10 text-sm font-medium hover:bg-foreground/85 transition-colors`.
- **Secondary CTA** (`Run DeepSWE`): `inline-flex items-center gap-1.5 border border-border px-4 h-10 text-sm hover:bg-muted/40 transition-colors`.
- Optional intro paragraph listing key advances (reference uses 4 bolded bullets: *Contamination free, High diversity, Real-world complexity, Reliable verification*).

### 6.3 Leaderboard
- Header `H2` "Leaderboard" + a count pill (e.g. `Models (12/16)`).
- **Horizontal bar rows:** rank · model label (family-colored) · score bar · `score%±ci%`.
- Bar track is `--muted`; fill tinted by `--family-*` color; width = score %.
- An **x-axis** with gridline labels: `0% 20% 40% 60% 80%` (and a `0% 25% 50% 75% 100%` variant).
- Scores shown in mono with confidence interval `±n%`.
- Rows are links to per-model detail.

> IRBG adaptation already implemented: bar fill uses a score-band gradient
> (indigo ≥80, blue ≥60, red <60) plus a grade badge. Optionally swap to
> `--family-*` tint to match the reference more literally.

### 6.4 Cards (task / scenario examples)
- `border border-border bg-card rounded-md`, padding `p-4`+.
- `H3` title (semibold), description in `--muted-foreground`, footer meta row with **repo/source** + a **language chip** colored via `--lang-*`.
- Laid out in a responsive grid; a trailing "All N tasks" link.
- IRBG: use for **scenario examples per pillar** (P1–P6) — title, prompt summary, pillar tag chip, mode tag (baseline/pressure/adversarial).

### 6.5 Buttons (canonical)
- Base: `inline-flex items-center justify-center whitespace-nowrap rounded-md font-medium transition-all disabled:pointer-events-none`.
- **Primary:** `bg-foreground text-background hover:bg-foreground/85`.
- **Outline:** `border border-border hover:bg-muted/40`.
- **Ghost/nav:** `text-muted-foreground hover:text-foreground`.
- Sizes: `h-9` (nav), `h-10 px-4 text-sm` (CTA).

### 6.6 Tables (blog data / results)
- Thin `border-b border-border` row separators (`/40` opacity for softer rules).
- Header cells `text-muted-foreground` `text-xs` medium; numeric cells mono, right-aligned.
- Used for: language distribution, score-vs-tokens/cost/duration, failure-mode tables.

### 6.7 Chips / Badges
- Language & family chips: small rounded fill in the family/lang color at low opacity with the color as text (`bg-*/10 text-* ring-1 ring-*/20`).
- IRBG grade badges follow this pattern: `A`=emerald, `B`=blue, `C`=yellow, `D`=orange, `F`=red.

### 6.8 Footer
- `border-t border-border`, muted text.
- Copyright (`© 2026 Datacurve`) + a link (`We're hiring`).
- Reference includes a **canary string** line (benchmark-contamination guard) in all-caps muted mono. IRBG may include an equivalent note.

---

## 7. Page Inventory (from references)

**Homepage `/`:** Header → Hero (title, tagline, CTAs, intro) → Leaderboard (bars + axis) → Task Examples grid → "Read the full blog" entry → Footer.

**Blog `/blog`:** Long-form article with a left section-nav and these `H2`s:
`Overview · Methodology · Results · Qualitative analysis · Limitations and future work · Acknowledgements · Citation`, plus a repeated Leaderboard and an `Explore` section. Rich `H3` subsections with embedded charts and tables (e.g. *Score vs. output tokens / wall-clock / cost per trial*, *Failure modes by model*, *Language distribution*).

**IRBG page map:**
- `/` — leaderboard + pillar legend + scenario examples *(implemented)*.
- `/model/[alias]` — per-model pillar breakdown + runs by mode *(implemented)*.
- `/methodology` (optional, blog-style) — the 6 pillars, scoring, run modes (baseline/pressure/adversarial), QA.

---

## 8. Tailwind v4 Theme Mapping (suggested `globals.css`)

```css
@import "tailwindcss";

@theme {
  --color-background: #151515;
  --color-foreground: oklch(98.5% 0 0);
  --color-card: #1d1d1d;
  --color-muted: #232323;
  --color-muted-foreground: oklch(72% 0 0);
  --color-border: #2a2a2a;
  --color-ring: oklch(50% 0 0);

  --color-pass: oklch(72% .16 155);
  --color-fail: oklch(70% .19 27);

  /* grades */
  --color-grade-a: oklch(72% .16 155);
  --color-grade-b: oklch(74% .16 250);
  --color-grade-c: oklch(80% .13 95);
  --color-grade-d: oklch(78% .14 50);
  --color-grade-f: oklch(70% .19 27);

  /* model families */
  --color-anthropic: oklch(78% .14 50);
  --color-openai:    oklch(75% .14 155);
  --color-google:    oklch(74% .16 255);
  --color-deepseek:  oklch(72% .17 295);
  --color-moonshot:  oklch(74% .17 20);
  --color-zhipu:     oklch(78% .12 195);

  --font-sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --font-mono: "Google Sans Code", ui-monospace, SFMono-Regular, Menlo, monospace;
}

html.dark, :root { color-scheme: dark; }
body { background: var(--color-background); color: var(--color-foreground); }
```

---

## 9. Quick Reference Cheatsheet

| Concern | Value |
|---|---|
| Canvas | `#151515` |
| Card | `#1d1d1d` |
| Border | `#2a2a2a` |
| Muted fill | `#232323` |
| Dim text | `oklch(72% 0 0)` |
| Primary text | `oklch(98.5% 0 0)` |
| Content width | `max-w-6xl mx-auto px-4` |
| Prose width | `max-w-[60ch]` |
| Radius | `rounded-md` |
| Transition | `0.15s cubic-bezier(.4,0,.2,1)` |
| Heading weight | 600, `tracking-tight` |
| Numerics | mono, right-aligned |
| Primary btn | `bg-foreground text-background h-10 px-4` |
| Outline btn | `border border-border hover:bg-muted/40` |

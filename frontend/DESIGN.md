# N.O.V.A — DESIGN.md

> Korean stock analysis & portfolio assistant. Mobile-first, AI-augmented, Toss-inspired clean aesthetic.

This document is the design source-of-truth. AI coding agents and human contributors should read it before writing UI. Built by synthesizing patterns from Coinbase (trust-focused fintech blue), Linear (precise minimalism), Wise (friendly clarity), and Toss (Korean fintech mobile-first).

---

## Overview

**Identity:** Calm, institutional, trustworthy. Not loud. Not gamified. A financial tool that respects the user's attention.

**Defaults:**
- Pure white canvas (light) / pure black canvas (dark)
- Toss-inspired bright blue primary, used sparingly
- Korean stock convention: red = up, blue = down (inverted from US/EU)
- Pretendard Variable for text, JetBrains Mono for tabular numbers
- 8pt spacing grid
- Pill-shaped primary CTAs (radius 100px)
- Card surfaces with shadow-sm by default, hairline-only on dense lists

**Anti-patterns:**
- No emoji decoration (use SF Symbols / Lucide icons instead)
- No rainbow palettes (Toss blue + grayscale + semantic red/blue only)
- No center-aligned body text
- No animations longer than 350ms
- No gradients on UI surfaces (only on hero illustrations if absolutely needed)
- No green for "up" — Korean users expect red

---

## Colors

### Brand & Accent
| Token | Light | Dark | Use |
|---|---|---|---|
| `--primary` | `#007AFF` | `#0A84FF` | Single brand action color. Primary CTAs, brand wordmark, focused links, active nav. |
| `--primary-active` | `#0066D6` | `#0072E0` | Pressed state of primary CTAs. |
| `--primary-soft` | `rgba(0,122,255,0.10)` | `rgba(10,132,255,0.12)` | Tinted backgrounds (badges, info banners, hover surfaces). |

> Notes: We use Apple SF iOS Blue (`#007AFF`) rather than Toss's exact `#3182F6` — visually nearly indistinguishable, but it pairs better with our existing dark-mode auto-switch. Treat them as interchangeable in spirit.

### Surface
| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `#F2F2F7` | `#000000` | Page-floor background. iOS-style grouped table. |
| `--surface` | `#FFFFFF` | `#1C1C1E` | Default card surface. Elevated content. |
| `--surface2` | `rgba(118,118,128,0.10)` | `rgba(118,118,128,0.18)` | Subtle fill behind chips, secondary buttons, skeletons. |
| `--surface3` | `rgba(118,118,128,0.16)` | `rgba(118,118,128,0.26)` | One step stronger than `--surface2`. Hovered chip backgrounds. |
| `--sep` | `rgba(60,60,67,0.12)` | `rgba(84,84,88,0.65)` | 0.5px / 1px hairline divider. |

### Text
| Token | Light | Dark | Use |
|---|---|---|---|
| `--label` | `#000000` | `#FFFFFF` | Primary text, headings, key numbers. |
| `--label2` | `#6C6C70` | `#EBEBF5` | Secondary body, meta info, captions. |
| `--label3` | `#AEAEB2` | `#6C6C70` | Disabled, placeholder, decorative micro-text. **Do not use for information that must be read** — see `feedback_label3_readability`. |

### Korean Stock Semantics (non-negotiable)
| Token | Value | Use |
|---|---|---|
| `--red` | `#FF3B30` (light) / `#FF453A` (dark) | **Price up, profit, golden cross, foreign net buy.** Korean convention. |
| `--primary` (blue) | as above | **Price down, loss, dead cross, foreign net sell.** Korean convention. |
| `--orange` | `#FF9500` / `#FF9F0A` | After-hours sessions, mild warnings. |
| `--green` | `#34C759` / `#30D158` | **Reserved for LIVE / 장중 indicator only.** Not for price up. |

**Critical:** Never use green for positive price change. Always red. Never use red for negative. This is the single most important rule in this document.

---

## Voice & Tone

The single biggest reason Toss feels like Toss is its **writing**, not its CSS. UI text in N.O.V.A follows the same principles.

### Conversational, not transactional

Bad: "평가손익"
Good: "오늘의 평가손익이에요"

Bad: "조건에 맞는 종목이 없습니다"
Good: "조건에 맞는 종목이 없어요"

Bad: "최고" / "최저"
Good: "수익 1위" / "손실 1위"

### Don't personify financial data

Stocks are not people. Don't say "가장 잘 가요" / "가장 힘들어요" — it reads as awkward marketing-speak in a financial context.

Bad: "오늘 가장 잘 가요" / "가장 힘들어요"
Good: "수익 1위" / "손실 1위"

Bad: "이 종목이 효자예요"
Good: "수익률 +12.3%"

Conversational ≠ personified. Friendly endings (~이에요/~해요) are good. Anthropomorphizing market data is not.

### Use `~이에요 / ~해요 / ~에요` endings
Never use `~입니다 / ~습니다 / ~합니다` in UI labels (formal-stiff). Use polite informal forms throughout.

### Time anchors
Prefix relevant labels with **"오늘의"** / **"지금"** / **"방금"** to make the data feel live and current:
- "오늘의 AI 브리핑"
- "지금 시세는요"
- "방금 추가했어요"

### Softer negatives
Avoid harsh negative phrasing for losses. Frame them as observations, not failures — but stick to data language, not emotion.

Bad: "큰 손실 발생"
Good: "지금 -8.5% 손실이에요"

Bad: "데이터 없음"
Good: "아직 정보가 없어요"

### Cap label length
Never exceed two lines. If a label is long, find a shorter way:

Bad: "보유하고 계신 모든 종목들의 평가손익 합계입니다"
Good: "보유 종목 N개의 평가손익이에요"

### Allowed (do this)
- 친근한 종결어미 (이에요, 해요)
- 시점어 (오늘, 지금, 방금, 어제)
- 부드러운 표현 (잘 가요, 힘들어요, 아쉬워요)
- 숫자 + 한국어 양사 ("3개", "N건")

### Forbidden (don't do this)
- 호칭 (어르신, 여러분, 당신) — see `feedback_no_honorifics_no_bold`
- 별표 markdown (`**굵게**`) — same memo
- 영어 UPPERCASE 라벨 ("LIVE" / "PRE" 같은 짧은 상태 배지만 예외)
- 형식 종결어미 (~입니다, ~합니다)
- 명령형 ("클릭하세요" → 대신 "탭하면 자세히 보여드려요")

### Worked examples (before → after)

| Context | Sterile | Toss-feel |
|---|---|---|
| Empty portfolio | "데이터 없음" | "아직 종목이 없어요" |
| Loading | "로딩 중" | "잠시만요…" |
| Search empty | "검색 결과 없음" | "찾으시는 종목이 없어요" |
| Confirm sell | "매도하시겠습니까?" | "정말 팔까요?" |
| Success | "저장 완료" | "저장했어요" |

---

## Typography

### Font Family
```
Primary  : "Pretendard Variable", Pretendard, -apple-system, BlinkMacSystemFont,
           "Apple SD Gothic Neo", "Noto Sans KR", sans-serif
Numbers  : "JetBrains Mono", "SF Mono", "Roboto Mono", monospace  /* tabular figures only */
```

- Pretendard handles Korean + Latin + numbers with consistent metrics. Default for everything except dense numeric tables.
- Use mono font for: stock prices in tables, percent changes in lists, time-series tooltips. **Not** for prices in single hero numbers (those use Pretendard with `font-feature-settings: "tnum"`).

### Hierarchy
| Token | Size | Weight | Line | Tracking | Use |
|---|---|---|---|---|---|
| `display-xl` | 36–44px | 800 | 1.05 | -0.04em | Hero P&L (large currency value) |
| `display-lg` | 28–32px | 800 | 1.08 | -0.035em | Section heroes (e.g. briefing headline) |
| `title-lg` | 22px | 700 | 1.2 | -0.025em | Panel titles, modal titles |
| `title-md` | 17px | 700 | 1.3 | -0.022em | Card titles, company names |
| `body-md` | 15px | 500 | 1.5 | -0.015em | Default body text. **Body baseline.** |
| `body-sm` | 13px | 500 | 1.5 | -0.01em | Secondary lists, descriptions |
| `caption` | 12px | 600 | 1.4 | 0 | Section labels, table column heads |
| `caption-strong` | 11px | 700 | 1.3 | 0 | Badge pills, ALL-CAPS chips |
| `micro` | 10px | 700 | 1.2 | 0.04em | Status badges (LIVE / 시간외 / 장전), tab icons |
| `number-hero` | 28–36px | 800 | 1.05 | -0.035em | Big currency display (P&L hero) — Pretendard with tnum |
| `number-md` | 15px | 800 | 1.2 | -0.035em | Stock price in row |
| `number-sm` | 11–12px | 700 | 1.2 | -0.02em | Change %, etc |

### Principles
- **Bold (700+) is reserved for primary information.** Body text stays at 500.
- **Negative letter-spacing on big numbers only.** `tracking-[-0.045em]` for hero numbers (28px+), `-0.035em` for medium numbers (18–24px), `-0.025em` for headings, `-0.015em` for body, 0 for small/caption.
- **Korean does not need uppercase or tracking tricks.** Don't apply `text-transform: uppercase` or wide letter-spacing to Korean labels — see `feedback_korean_label_typography`. Use weight/color for hierarchy instead.
- **Number alignment:** Right-aligned in tables. Use one of:
  - **Inline React style:** `style={{ fontVariantNumeric: "tabular-nums" }}` ← preferred for one-off numbers
  - **CSS class:** `font-feature-settings: "tnum"` ← preferred in stylesheets
  - **Mono font:** Switch family to `"JetBrains Mono", monospace` when many numbers need to align in a dense column (asset tables, price columns)
- **`tabular-nums` is required for any number that can change in place** — hero P&L, live prices, percent changes. Without it, the value shifts horizontally as digits change.

---

## Layout

### Spacing Grid
Base unit: **4px**. Use multiples: 4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48 / 64.

| Use | Value |
|---|---|
| Tight (icon ↔ label inside chip) | 4–6px |
| Related elements within a card | 8–12px |
| Between rows in a list | 0 (hairline-separated) |
| Card internal padding | 16–20px |
| Card group spacing (between cards) | 12–16px |
| Section padding (above/below) | 24–32px |
| Page edge padding (mobile) | 16px |
| Page edge padding (desktop) | 16–24px |

### Tap Targets
**Minimum 44×44pt on mobile.** Use the `.touch-target::after` invisible expansion pattern when visual size must be smaller (see globals.css).

### Grid (Desktop)
Three-panel layout: `1fr 1fr 1fr` with 1px separators. Panels: Portfolio | Watchlist | Chat. Each panel is independently scrollable.

### Grid (Mobile, ≤768px)
Single-column. Panels swap via bottom tab bar. Tab bar height: `56px + env(safe-area-inset-bottom)`. Ticker strip (40px) above panel area for KOSPI/KOSDAQ visibility.

### Container Widths
Cards are full-width within their panel — no max-width constraint inside the dashboard. Modals: `min(560px, 92vw)` for forms, `min(720px, 96vw)` for detail views.

---

## Elevation & Depth

Four tiers (already defined in globals.css):

| Token | Use |
|---|---|
| `--shadow-sm` | Default card. `0 1px 2px rgba(0,0,0,0.04), 0 1px 6px rgba(0,0,0,0.03)` |
| `--shadow` | Mid-level (hover, lifted card) |
| `--shadow-md` | Floating elements (dropdowns, popovers) |
| `--shadow-lg` | Modals, sheets |

**Dark mode** uses heavier shadows because the contrast against dark surfaces requires more lift.

Use **hairlines instead of shadows** for in-list separation (dense rows). Reserve shadow for actual elevation (cards above page floor, modals above content).

---

## Shapes

### Border Radius Scale
| Token | Value | Use |
|---|---|---|
| `radius-sm` | 4–6px | Inline pills, small badges |
| `radius-md` | 8–10px | Inputs, secondary buttons |
| `radius-lg` | 12–14px | Cards, content blocks |
| `radius-xl` | 16–20px | Hero cards, modal sheets |
| `radius-pill` | 100px | Primary CTAs, chips, filter pills |
| `radius-full` | 9999px | Avatars, circular icon plates |

**Default for new components:** `12px` (cards), `100px` (action buttons), `8px` (inputs).

### Borders
- **0.5px hairlines** on light mode (uses `var(--sep)`)
- **1px** in dark mode automatically via media query
- **Never use 2px borders** except for focused input rings

---

## Components

The patterns below describe N.O.V.A's actual components. When adding new UI, match the closest pattern below before inventing new geometry.

### Primary Button
**Use:** All primary CTAs.
- Background `--primary`, text white (`#FFFFFF`)
- Height 48px (mobile) / 44px (desktop dense)
- Padding `12px 20px`
- Radius 100px (pill)
- Font: 16px weight 700
- Active state: `--primary-active` background + `transform: scale(0.97)` + `opacity: 0.68`
- Disabled: `opacity: 0.4`, cursor not-allowed

### Secondary Button
- Background `--surface2`, text `--label`
- Same geometry as primary
- For "취소", "초기화", "닫기"-style actions

### Tinted Button
- Background `rgba(0,122,255,0.10)`, text `--primary`, weight 700
- Sized smaller than primary: height 28–32px, padding `6px 12px`, radius 100px
- Font: 12px weight 700
- Sits between Primary and Ghost in visual weight
- For inline secondary actions inside cards: "새로고침", "더 보기", "다시 시도"

### Ghost / Text Button
- Transparent background, text `--primary`
- Padding `8px 12px` (smaller, less prominent)
- For "더 보기", "다시 시도", "전체 보기"-style links inside paragraphs

### Chip / Filter Pill
- Background `--surface` (inactive) / `--primary` (active)
- Text `--label` (inactive) / white (active)
- Height ~28px, padding `5px 12px`
- Radius 100px, border `1.5px solid var(--sep)` when inactive
- Used in: ScreenerCard (sector/RSI/MA filters), tab bars

### Card
- Background `--surface`
- Radius 16–20px
- Padding 16–20px
- Shadow `--shadow-sm`
- **No border** by default (shadow provides separation)
- Used for: stock rows container, briefing card, screener results

### Sentiment-Tinted Card
**Use:** Hero KPI containers where the metric implies positive/negative sentiment (P&L, today's gain, etc).
- Background uses 5–6% alpha tint of the semantic color:
  - Positive (profit): `rgba(255,59,48,0.05)` (light) / `rgba(255,69,58,0.08)` (dark)
  - Negative (loss): `rgba(0,122,255,0.05)` (light) / `rgba(10,132,255,0.08)` (dark)
  - Neutral: `--surface2`
- Border `0.5px solid var(--sep)`
- Radius 16px, padding `18px`
- The semantic color carries through to the hero number AND the tint background — they reinforce each other

### Hero KPI Block
**Use:** Display ONE critical metric prominently (today's P&L, total return, account balance). Always placed at the top of a screen or card.

Anatomy (top to bottom):
1. **Friendly label** — 12px / weight 600 / `--label2` / `letter-spacing: -0.01em` / margin-bottom 6–8px
   - Phrase as a casual sentence: "보유 종목 N개의 평가손익이에요"
2. **Hero number** — 36–42px / weight 800 / sentiment color / `letter-spacing: -0.045em` / `line-height: 1.05` / `fontVariantNumeric: "tabular-nums"`
   - For percent: `{val > 0 ? "+" : ""}{val.toFixed(2)}%`
   - For currency: `{val > 0 ? "+" : ""}{val.toLocaleString("ko-KR")}원`
3. **Optional sub-stat row** — flexbox row of 2–3 sub cells with hairline separator
   - Each sub cell: small label (11px / `--label3`), small name (13px / 700), small number (15px / 800 / sentiment color)

Place inside a `Sentiment-Tinted Card`. Never standalone.

### Status Chip (Sentiment Pill)
- Sub-pill placed inline next to a title to signal status (e.g. "긍정적", "주의", "중립")
- Background: 20% alpha of the sentiment color (`${sentColor}20` works as hex8 if base is hex)
- Text: same sentiment color, 10px weight 700
- Padding `2px 7px`, radius 6px

### List Row (Stock Row)
- Inside a card, no individual border
- Hairline divider `0.5px solid var(--sep)` between rows
- Padding `11px 16px`
- Tap target: full row (minimum 44px height)
- Structure: logo (32–40px) · name+meta (flex:1, min-width:0) · sparkline (44×24, optional) · price+change (right-aligned, ~70px)

### Stock Inline Insight (한 줄 인사이트)
- 11px weight 600, single line, ellipsis
- Color matches `tone`:
  - `positive` → `--red`
  - `negative` → `--primary`
  - `neutral` → `--label3`
- Leading 3×3 dot in `currentColor`
- Placed below P&L line in the stock row

### Status Badge (LIVE / 시간외 / 장전 / 목표 / 손절)
- Tiny pill: padding `1px 5px`, radius 4px
- Font: 8px weight 700
- Color + soft tinted background:
  - LIVE → `--green` on `rgba(52,199,89,0.13)`
  - 시간외 → `--orange` on `rgba(255,149,0,0.13)`
  - 장전 → `#5AC8FA` on `rgba(90,200,250,0.13)`
  - 목표 → `--red` on `rgba(255,59,48,0.10)`
  - 손절 → `--primary` on `rgba(0,122,255,0.10)`

### Market Index Badge (KOSPI / KOSDAQ)
- Pill in ticker strip
- Background `--surface2`, border `0.5px solid var(--sep)`
- Inline: name (11px) · value (13px weight 800) · change% (11px weight 700, colored)
- The value span uses `usePriceFlash` for live update flash

### Input
- Background `--bg` (inset) or `--surface` (raised)
- Height 48px (mobile) / 40px (desktop)
- Padding `8px 12px`
- Radius 8px
- Font: **must** be ≥ 16px on mobile (iOS zoom prevention — handled by `globals.css` media query)
- Focus: 2px border `--primary`, no outline ring

### Typing / Loading Indicator
- 3-dot bounce animation (`@keyframes bounce` already defined)
- 7×7px dots, color `--label2`, gap 4px
- Use for AI streaming "thinking" state, before first token arrives

### Streaming Text
- During SSE token streaming, render incrementally without cursor blink
- Smoothing handled by CSS (no JS animation)
- Sources/companies appear AT START via metadata event; text streams below

### Modal
- Background `--surface` (NOT `--surface2` — must be opaque, see `feedback_css_surface_transparency`)
- Backdrop `rgba(0,0,0,0.4)` with `backdrop-filter: blur(8px)`
- Mobile: bottom sheet, `border-radius: 20px 20px 0 0`, slide-up animation
- Desktop: centered, `border-radius: 16px`, scale-in animation
- Close: dedicated X button + backdrop-tap + ESC. Always provide explicit escape — see `feedback_modal_escape_hatch`.

### AI Source Badge (`SourceBadges`)
- Below assistant response
- 11px weight 600, `--label2` color
- Single line collapse/expand toggle ("참고 자료 N건 ▼")
- Expanded: each source as a 10px-radius card with snippet + label

### AI Synced Companies Badge
- Blue pill (`var(--primary)` on `rgba(0,122,255,0.08)`)
- Placed below the assistant response, aligned with same `marginLeft: 34` as response text (set by the PARENT — never inside the badge component)

### Treemap (Allocation)
- Squarified cells, sized by allocation %
- Color = P&L (gradient from `rgba(255,59,48,0.28)` to `rgba(255,59,48,0.83)` for profits; same for `rgba(0,122,255,...)` for losses)
- Cell label thresholds:
  - ≥64×36px → name + allocation% + P&L%
  - ≥36×22px → allocation% only
  - smaller → tooltip only
- Click → opens StockDetailModal

### Price Flash (Live Update)
- 0.6s animation (`@keyframes price-flash-up` / `price-flash-down`)
- Background `rgba(255,59,48,0.22)` → transparent (up), `rgba(0,122,255,0.22)` → transparent (down)
- Apply via `className={`price-flash-${flash}`}` from `usePriceFlash` hook
- Use on: stock row current price, market index value

---

## Do's and Don'ts

### Do
- **Use red for up, blue for down.** Always. Even in dark mode.
- **Rewrite every UI label in the Toss voice** before shipping — see Voice & Tone above. The biggest single difference between "Toss-like" and "sterile fintech app" is this.
- **Use `fontVariantNumeric: "tabular-nums"` on every number that can change** — hero P&L, prices, percentages.
- **Use weight (700/800) for hierarchy** instead of size jumps.
- **Hide development metadata in production** — distance scores, chunk counts, vector DB messages. See `feedback_hide_dev_stats_in_ui`.
- **Provide an escape from every modal** — X button minimum. See `feedback_modal_escape_hatch`.
- **Confirm sell trades use current price**, not buy price — see `feedback_sell_price_at_trade_time`.
- **Reserve `--label3` for decoration** (separators, placeholders). Use `--label2` for content people need to read.
- **Use SF Symbols / Lucide for UI icons.** Reserve emoji for decoration or streaks (see `feedback_sf_symbols_over_emoji`).
- **Test in dark mode** before considering a feature done.

### Don't
- Don't use green for price up.
- Don't apply iOS Safari zoom-fix CSS (`font-size: max(16px, 1em) !important`) outside the mobile media query — it overrides desktop inline styles.
- Don't use semitransparent `--surface2` / `--surface3` for modal backgrounds — they show the page behind.
- Don't compose `marginLeft` in both parent and child of the same vertical stack (creates double-offset).
- Don't use `text-transform: uppercase` or wide letter-spacing on Korean labels.
- Don't animate layout-affecting properties (height, width) — animate `opacity`, `transform` only.
- Don't add honorifics (어르신, 여러분, 당신) to AI responses, and don't use `**`-style markdown bold. See `feedback_no_honorifics_no_bold`.
- Don't use `eslint-disable` to silence linter warnings — fix the underlying issue.

---

## Responsive Behavior

### Breakpoint
A single breakpoint: **768px**.
- `≤768px` → mobile (single column, bottom tab bar, ticker strip visible)
- `>768px` → desktop (3-panel grid, no ticker strip)

### Mobile-First Specifics
- Tab bar height includes `env(safe-area-inset-bottom)` — never collapse them
- Ticker strip horizontally scrollable (`overflow-x: auto`, momentum scroll, scrollbar hidden)
- Hide `.nova-tagline`, `.header-market-status`, `.panel-header-subtitle` on mobile
- Inputs forced to ≥16px font on mobile only (zoom prevention)
- Touch targets: invisible `.touch-target::after { inset: -6px }` for small icon buttons

### Desktop Specifics
- 3-panel grid uses `1fr 1fr 1fr` with 1px gap of `--sep`
- Panels independently scroll
- Hover states active (mobile has none)
- Keyboard nav: ESC closes modals, Enter submits forms

---

## Iteration Guide

When introducing new UI:

1. **Match existing components first.** If you can express the new feature with a `Card + StockRow` or `Modal + form` composition, do that.
2. **Pick from this document's color/type tokens.** Do not introduce new hex values.
3. **Respect Korean conventions.** Red/blue inversion, no honorifics, no excessive English UPPERCASE.
4. **Test both light and dark mode** before opening a PR.
5. **Test on iPhone Safari** (real device or simulator) — iOS has unique font-size/safe-area quirks.

When the document drifts from reality, update it. This file is not aspirational — it should describe what is, with notes on what to avoid.

---

## Known Gaps

The following areas are intentionally open-ended for now:

- **Onboarding / empty states** — current empty states are functional but lack a unified illustration style. Picking one (e.g. line-art icon system) is a future task.
- **Chart styling** — sparklines exist but stock detail charts (StockDetailModal) need a defined style. Currently ad-hoc.
- **Notification panel** — visual hierarchy of unread alerts vs. read alerts not yet codified.
- **Dashboard home (planned)** — see project memory `[[project_nova_uxplan]]` item ⑥. To be designed.

When implementing any of these, propose a pattern that fits this document's existing tokens, then update this doc with the new component spec.

---

## Credits

- **Primary inspiration:** Toss (toss.im), the gold standard for Korean fintech mobile UI.
- **Pattern references:** Coinbase (trust-focused blue, pill CTAs), Linear (precise minimalism, depth tiers), Wise (friendly typographic clarity). Public DESIGN.md analyses sourced from [getdesign.md](https://getdesign.md).
- All trademarks belong to their respective owners. This document describes N.O.V.A's own UI; it does not reproduce any other product's proprietary design.

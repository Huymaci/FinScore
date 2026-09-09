---
name: design-system-modern-finance-dashboard-ui-moneyboard-by-ridoy-
description: Creates implementation-ready design-system guidance with tokens, component behavior, and accessibility standards. Use when creating or updating UI rules, component specifications, or design-system documentation.
---

<!-- TYPEUI_SH_MANAGED_START -->

# 💳 Modern Finance Dashboard UI – MoneyBoard by Ridoy Ahmed for Arobix Studio on Dribbble

## Mission
Deliver implementation-ready design-system guidance for 💳 Modern Finance Dashboard UI – MoneyBoard by Ridoy Ahmed for Arobix Studio on Dribbble that can be applied consistently across dashboard web app interfaces.

## Brand
- Product/brand: 💳 Modern Finance Dashboard UI – MoneyBoard by Ridoy Ahmed for Arobix Studio on Dribbble
- URL: https://dribbble.com/shots/27173313--Modern-Finance-Dashboard-UI-MoneyBoard
- Audience: authenticated users and operators
- Product surface: dashboard web app

## Style Foundations
- Visual style: structured, accessible, implementation-first
- Main font style: `font.family.primary=Mona Sans`, `font.family.stack=Mona Sans, Helvetica Neue, Helvetica, Arial, sans-serif`, `font.size.base=14px`, `font.weight.base=400`, `font.lineHeight.base=28px`
- Typography scale: `font.size.xs=10px`, `font.size.sm=11px`, `font.size.md=12px`, `font.size.lg=13px`, `font.size.xl=13.33px`, `font.size.2xl=14px`, `font.size.3xl=16px`, `font.size.4xl=20px`
- Color palette: `color.text.primary=#0d0c22`, `color.text.secondary=#6e6d7a`, `color.text.tertiary=#060318`, `color.surface.muted=#ffffff`, `color.surface.base=#000000`, `color.surface.strong=#ece2dc`
- Spacing scale: `space.1=6px`, `space.2=7px`, `space.3=8px`, `space.4=10px`, `space.5=14px`, `space.6=16px`, `space.7=18.5px`, `space.8=20px`
- Radius/shadow/motion tokens: `radius.xs=4px`, `radius.sm=6px`, `radius.md=8px`, `radius.lg=12px`, `radius.xl=50px`, `radius.2xl=10000000px` | `motion.duration.instant=50ms`, `motion.duration.fast=100ms`, `motion.duration.normal=200ms`

## Accessibility
- Target: WCAG 2.2 AA
- Keyboard-first interactions required.
- Focus-visible rules required.
- Contrast constraints required.

## Writing Tone
concise, confident, implementation-focused

## Rules: Do
- Use semantic tokens, not raw hex values in component guidance.
- Every component must define required states: default, hover, focus-visible, active, disabled, loading, error.
- Responsive behavior and edge-case handling should be specified for every component family.
- Accessibility acceptance criteria must be testable in implementation.

## Rules: Don't
- Do not allow low-contrast text or hidden focus indicators.
- Do not introduce one-off spacing or typography exceptions.
- Do not use ambiguous labels or non-descriptive actions.

## Guideline Authoring Workflow
1. Restate design intent in one sentence.
2. Define foundations and tokens.
3. Define component anatomy, variants, and interactions.
4. Add accessibility acceptance criteria.
5. Add anti-patterns and migration notes.
6. End with QA checklist.

## Required Output Structure
- Context and goals
- Design tokens and foundations
- Component-level rules (anatomy, variants, states, responsive behavior)
- Accessibility requirements and testable acceptance criteria
- Content and tone standards with examples
- Anti-patterns and prohibited implementations
- QA checklist

## Component Rule Expectations
- Include keyboard, pointer, and touch behavior.
- Include spacing and typography token requirements.
- Include long-content, overflow, and empty-state handling.

## Quality Gates
- Every non-negotiable rule must use "must".
- Every recommendation should use "should".
- Every accessibility rule must be testable in implementation.
- Prefer system consistency over local visual exceptions.

<!-- TYPEUI_SH_MANAGED_END -->

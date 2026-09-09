---
name: design-system-banking-dashboard-ui-design-by-nixtio-on-dribbbl
description: Creates implementation-ready design-system guidance with tokens, component behavior, and accessibility standards. Use when creating or updating UI rules, component specifications, or design-system documentation.
---

<!-- TYPEUI_SH_MANAGED_START -->

# Banking Dashboard UI Design by Nixtio on Dribbble

## Mission
Deliver implementation-ready design-system guidance for Banking Dashboard UI Design by Nixtio on Dribbble that can be applied consistently across dashboard web app interfaces.

## Brand
- Product/brand: Banking Dashboard UI Design by Nixtio on Dribbble
- URL: https://dribbble.com/shots/27627802-Banking-Dashboard-UI-Design
- Audience: authenticated users and operators
- Product surface: dashboard web app

## Style Foundations
- Visual style: structured, accessible, implementation-first
- Main font style: `font.family.primary=Mona Sans`, `font.family.stack=Mona Sans, Helvetica Neue, Helvetica, Arial, sans-serif`, `font.size.base=14px`, `font.weight.base=400`, `font.lineHeight.base=28px`
- Typography scale: `font.size.xs=11px`, `font.size.sm=12px`, `font.size.md=13px`, `font.size.lg=13.33px`, `font.size.xl=14px`, `font.size.2xl=16px`, `font.size.3xl=20px`, `font.size.4xl=24px`
- Color palette: `color.text.primary=#0d0c22`, `color.text.secondary=#6e6d7a`, `color.text.tertiary=#060318`, `color.surface.muted=#ffffff`, `color.surface.base=#000000`, `color.surface.strong=#fdfdfd`
- Spacing scale: `space.1=5px`, `space.2=6px`, `space.3=7px`, `space.4=8px`, `space.5=10px`, `space.6=14px`, `space.7=16px`, `space.8=18.5px`
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

# Simplex LP Solver (step-by-step, Row-0 form)

Companion to `graphical-lp-solver`: instead of solving 2-variable LPs
geometrically, this walks through the **simplex method** the way you would
write it by hand — any number of variables, max or min, and any
mix of `<=`, `>=`, and `=` constraints.

## Tableau convention

This solver uses the **Row 0 (Z-row) form** (Hillier & Lieberman style):
the objective is rewritten as the equation

```
Z - c1*x1 - c2*x2 - ... (+/- M*artificials) = 0
```

and carried as Row 0 of every tableau. The entering-variable rules are:

- **max**: enter the most NEGATIVE Row 0 coefficient; optimal when all >= 0
- **min**: enter the most POSITIVE Row 0 coefficient; optimal when all <= 0

(The other common layout — the Cj / Zj / Cj−Zj "net evaluation" tableau of
Taha-style texts — carries the same numbers with opposite sign:
Row-0 coefficient = Zj − Cj = −(Cj − Zj). Every pivot and every answer is
identical; only the bookkeeping differs.)

## What it does

1. **Step 0 – Problem as given** — echoes back the LP.
2. **Step 1 – Preprocessing** — any negative right-hand side is multiplied
   by −1 (flipping the sense), then the method is chosen:
   - all `<=` → ordinary simplex (slacks give the starting basis)
   - any `>=` or `=` → **Big-M method** (artificial variables required)
3. **Step 2 – Standard form** — slack (`s`), surplus (`e`), and artificial
   (`a`) variables are added with an explanation of why each is needed; the
   objective is moved to the left-hand side to form Row 0 (this is where
   the coefficients change sign); for Big-M problems the basic artificial
   variables are eliminated from Row 0 ("proper form") with the row
   operations shown.
4. **Step 3 – Iterations** — every tableau printed with Row 0 on top;
   entering variable and why, minimum-ratio test row by row, leaving
   variable, pivot element marked `[ ]`, and the explicit row operations
   including the Row 0 update (`New R0 = R0 - (4M-3) × New R2`, ...).
5. **Step 4 – Solution** — decision-variable values, optimal Z (Row 0's
   RHS), binding-constraint / slack interpretation, and detection of the
   special cases: **unbounded**, **infeasible** (artificial stuck in the
   basis), **degeneracy**, and **alternate optima**.

All arithmetic is exact (`fractions.Fraction`), and the Big-M penalty stays
symbolic, so Row 0 entries look like `4M-3` — exactly what you would write
on paper.

## Running it

Only the standard library is required:

```
python simplex_lp_solver.py
```

If `scipy` is installed, the final answer is cross-checked against
`scipy.optimize.linprog`.

Inputs accept integers, decimals, or fractions (`3`, `2.5`, `7/2`).
Answer `y` to "Pause after each step?" to advance tableau-by-tableau with
the Enter key while following along by hand.

## Future work

- `--style cjzj` (or `--style both`): print each tableau in the Cj / Zj / Cj−Zj
  "net evaluation" convention alongside (or instead of) Row-0, for
  cross-training between the engineering and business-school notations. The
  numbers already exist in the tableau — this is a display transform
  (Cj−Zj row = negated Row-0 coefficients; Zj = Cj − (Cj−Zj); add the CB
  column from the current basis costs).

## Browser version

A no-install browser port of this same Row-0 Big-M engine lives at the repo
root as [`lab.html`](../../lab.html). It carries the same
tableau convention, exact fractions, symbolic M, and entering/leaving rules,
adds a step-through UI plus a graphical view, and includes a "Your problem"
tab that takes typed coefficients the way this script takes console input.

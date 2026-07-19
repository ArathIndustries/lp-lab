# LP Lab

Interactive tools and console solvers for linear programming: formulation,
the graphical method, the simplex method, and the Big-M method. All tableau
arithmetic is exact — `BigInt` fractions in the browser, `fractions.Fraction`
in Python — and the Big-M penalty stays symbolic, so Row 0 entries read
`4M−3` exactly as written by hand.

Live pages: <https://arathindustries.github.io/lp-lab/>

## Contents

| Piece | What it is |
|---|---|
| [`lab.html`](https://arathindustries.github.io/lp-lab/lab.html) | Interactive workbench: live simplex / Big-M tableaus with step-through pivots, an SVG graphical view (constraint lines → feasible region → corner points → optimum), and a "Your problem" tab that solves typed coefficients. Runs fully offline. |
| [`trainer.html`](https://arathindustries.github.io/lp-lab/trainer.html) | Guided trainer: each walkthrough starts from the raw problem and builds the tableau step by step (standard form → Row 0 → Big-M elimination → iterate), plus a generator that produces fresh problems with a chosen outcome (unique, alternate optima, degenerate, unbounded, infeasible). |
| [`cheatsheet.html`](https://arathindustries.github.io/lp-lab/cheatsheet.html) | One-side reference: formulation, graphical, simplex, Big-M (Winston Row-0 form). |
| [`cheatsheet_algo.html`](https://arathindustries.github.io/lp-lab/cheatsheet_algo.html) | One-side reference organized as a single procedure with decision points. |
| [`solvers/simplex/`](solvers/simplex/) | Console Big-M simplex solver: any number of variables, max or min, any mix of `<=` / `>=` / `=`. Prints every tableau, ratio test, and row operation. Standard library only; cross-checks against `scipy.optimize.linprog` when scipy is installed. |
| [`solvers/graphical/`](solvers/graphical/) | Console graphical-method solver for 2-variable LPs. Prints the algebraic corner-point solution and renders `graph_solution.png` plus an animated constraint build-up GIF (requires matplotlib/numpy — see its README). |

## Design: exact arithmetic, symbolic M

Floating point misclassifies ties in the ratio test and zeros in Row 0 —
the two comparisons that decide pivots, degeneracy, and alternate optima.
Both the browser engine and the Python solver therefore use exact rational
arithmetic, and represent Big-M coefficients as pairs (rational multiple of
M, rational constant) compared lexicographically. Consequences:

- Tableau entries are exact fractions (`3/2`, `-7/4`), never `1.4999999`.
- Row 0 under Big-M prints symbolically (`4M−3`), matching hand work.
- Infeasibility is detected structurally (artificial basic at a positive
  value), not by a numeric threshold.

The browser and console solvers share the same Row-0 conventions and
pivot rules; the HTML pages state the verification cases (Giapetto,
Dakota z=280, Bevco z=25 and infeasible variant, Winston Ex 4.6 z=−12).

## Running the Python solvers

Simplex (standard library only):

```
python solvers/simplex/simplex_lp_solver.py
```

Prompts for max/min, objective coefficients, and constraints; accepts
integers, decimals, or fractions (`3`, `2.5`, `7/2`). Answer `y` to
"Pause after each step?" to advance tableau-by-tableau.

Graphical (needs matplotlib/numpy):

```
cd solvers/graphical
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows
.venv/Scripts/python graphical_lp_solver.py
```

## Tableau convention

Row 0 (Z-row) form: the objective is carried as
`Z − c₁x₁ − c₂x₂ − … (± M·artificials) = 0`. Max enters the most negative
Row 0 coefficient; min enters the most positive. The Cj−Zj "net evaluation"
layout used by other texts carries the same numbers with opposite sign;
see `solvers/simplex/README.md`.

---

A Forged Tool · © Arath Industries

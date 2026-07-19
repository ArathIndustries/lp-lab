# Graphical LP Solver

Console-driven graphical-method solver for 2-variable linear programs.
Prompts for the objective and constraints, prints a step-by-step algebraic
solution, and produces `graph_solution.png` (static) and `graph_animation.gif`
(constraint build-up + objective-line sweep).

## Setup

```
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows
# .venv/bin/python -m pip install -r requirements.txt     # macOS / Linux
```

## Run

```
python graphical_lp_solver.py
```

Enter `max` or `min`, the objective coefficients, then each constraint as
`a1  a2  sense  b`. Non-negativity (x1>=0, x2>=0) is added automatically.

## Notes

- 2 decision variables only (graphical method requirement).
- Assumes a bounded, non-empty feasible region.
- Verified against `scipy.optimize.linprog` on each run (printed after Step 4).

## Browser version

A no-install browser port of this corner-point method lives at the repo root
as [`lab.html`](../../lab.html). Its Graphical tab steps
through axes → constraint lines → shaded feasible region → labeled corner
points with objective values → optimum, and unlike this script it also
handles unbounded and infeasible cases visually.

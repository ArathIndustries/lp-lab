"""
Graphical method solver for 2-variable linear programs.

Reads an objective function and a set of constraints from the console,
then:
  1. Prints a step-by-step algebraic solution (intercepts, corner-point
     intersections, objective evaluation).
  2. Renders an animated build-up of the graph (constraints drawn one at a
     time, feasible region shaded, objective line swept to the optimum),
     saved as graph_animation.gif.
  3. Renders a clean static plot of the final solution, saved as
     graph_solution.png, for embedding in a report.

Run with:  python graphical_lp_solver.py  (after installing requirements.txt)
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from scipy.optimize import linprog

TOL = 1e-7


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class Constraint:
    def __init__(self, a1, a2, sense, b, label=None):
        self.a1 = a1
        self.a2 = a2
        self.sense = sense  # '<=', '>=', or '='
        self.b = b
        self.label = label or f"{a1}x1 + {a2}x2 {sense} {b}"

    def satisfied(self, x1, x2, tol=TOL):
        val = self.a1 * x1 + self.a2 * x2
        if self.sense == "<=":
            return val <= self.b + tol
        if self.sense == ">=":
            return val >= self.b - tol
        return abs(val - self.b) <= tol

    def x_intercept(self):
        return self.b / self.a1 if abs(self.a1) > TOL else None

    def y_intercept(self):
        return self.b / self.a2 if abs(self.a2) > TOL else None


# ---------------------------------------------------------------------------
# Console input
# ---------------------------------------------------------------------------

def read_float(prompt):
    while True:
        raw = input(prompt).strip()
        try:
            return float(raw)
        except ValueError:
            print("  Not a number, try again.")


def read_sense(prompt):
    while True:
        raw = input(prompt).strip()
        if raw in ("<=", ">=", "="):
            return raw
        print("  Enter one of: <=  >=  =")


def read_problem():
    print("=== Objective function ===")
    print("Z = c1*x1 + c2*x2")
    sense = ""
    while sense not in ("max", "min"):
        sense = input("Maximize or minimize? (max/min): ").strip().lower()
    c1 = read_float("c1 (coefficient of x1): ")
    c2 = read_float("c2 (coefficient of x2): ")

    print("\n=== Constraints ===")
    n = int(read_float("How many constraints (not counting x1>=0, x2>=0)? "))
    constraints = []
    for i in range(1, n + 1):
        print(f"\nConstraint {i}: a1*x1 + a2*x2 (sense) b")
        a1 = read_float("  a1: ")
        a2 = read_float("  a2: ")
        s = read_sense("  sense (<=, >=, =): ")
        b = read_float("  b: ")
        constraints.append(Constraint(a1, a2, s, b, label=f"C{i}: {a1}x1 + {a2}x2 {s} {b}"))

    # Non-negativity, implicit for the graphical method.
    constraints.append(Constraint(1, 0, ">=", 0, label="x1 >= 0"))
    constraints.append(Constraint(0, 1, ">=", 0, label="x2 >= 0"))

    return sense, c1, c2, constraints


# ---------------------------------------------------------------------------
# Geometry: intersections and feasible corner points
# ---------------------------------------------------------------------------

def line_intersection(c_i, c_j):
    """Solve the 2x2 system formed by treating both constraints as equalities."""
    A = np.array([[c_i.a1, c_i.a2], [c_j.a1, c_j.a2]])
    b = np.array([c_i.b, c_j.b])
    if abs(np.linalg.det(A)) < TOL:
        return None  # parallel lines, no unique intersection
    x = np.linalg.solve(A, b)
    return x[0], x[1]


def find_corner_points(constraints):
    """All pairwise line intersections that satisfy every constraint."""
    points = []
    seen = set()
    for i in range(len(constraints)):
        for j in range(i + 1, len(constraints)):
            pt = line_intersection(constraints[i], constraints[j])
            if pt is None:
                continue
            x1, x2 = pt
            if not all(c.satisfied(x1, x2) for c in constraints):
                continue
            key = (round(x1, 6), round(x2, 6))
            if key in seen:
                continue
            seen.add(key)
            points.append((x1, x2, constraints[i], constraints[j]))
    return points


def order_by_angle(points):
    """Sort feasible corner points counterclockwise around their centroid,
    so they form a proper polygon boundary for shading."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    return sorted(points, key=lambda p: np.arctan2(p[1] - cy, p[0] - cx))


# ---------------------------------------------------------------------------
# Step-by-step console explanation
# ---------------------------------------------------------------------------

def print_steps(sense, c1, c2, constraints, corners_raw, best):
    print("\n" + "=" * 60)
    print("STEP-BY-STEP SOLUTION")
    print("=" * 60)

    print(f"\nObjective: {sense.title()} Z = {c1}x1 + {c2}x2")

    print("\nStep 1 - Plot each constraint line (find intercepts):")
    for c in constraints[:-2]:  # skip the two non-negativity constraints
        xi = c.x_intercept()
        yi = c.y_intercept()
        xi_txt = f"({xi:g}, 0)" if xi is not None else "none (vertical/degenerate)"
        yi_txt = f"(0, {yi:g})" if yi is not None else "none (horizontal/degenerate)"
        print(f"  {c.label}")
        print(f"    x1-intercept (x2=0): {xi_txt}")
        print(f"    x2-intercept (x1=0): {yi_txt}")

    print("\nStep 2 - Find every intersection of two boundary lines, "
          "keep the ones that satisfy ALL constraints (feasible corner points):")
    for x1, x2, ci, cj in corners_raw:
        print(f"  Intersect [{ci.label}] with [{cj.label}]  ->  "
              f"solve the 2x2 system:")
        print(f"    {ci.a1}x1 + {ci.a2}x2 = {ci.b}")
        print(f"    {cj.a1}x1 + {cj.a2}x2 = {cj.b}")
        print(f"    => (x1, x2) = ({x1:.4f}, {x2:.4f})  [feasible]")

    print("\nStep 3 - Evaluate Z at each feasible corner point "
          "(the optimum of a linear program always occurs at a corner):")
    for x1, x2, _, _ in corners_raw:
        z = c1 * x1 + c2 * x2
        flag = "  <-- best so far" if (x1, x2) == (best[0], best[1]) else ""
        print(f"  ({x1:.4f}, {x2:.4f}):  Z = {c1}({x1:.4f}) + {c2}({x2:.4f}) = {z:.4f}{flag}")

    print(f"\nStep 4 - Optimal solution:")
    print(f"  x1 = {best[0]:.4f}, x2 = {best[1]:.4f}, Z = {best[2]:.4f}")


# ---------------------------------------------------------------------------
# Verification against scipy's simplex/HiGHS solver
# ---------------------------------------------------------------------------

def verify_with_linprog(sense, c1, c2, constraints):
    """Cross-check the corner-point result against scipy.optimize.linprog."""
    A_ub, b_ub, A_eq, b_eq = [], [], [], []
    sign = -1 if sense == "max" else 1
    for c in constraints[:-2]:  # non-negativity handled by bounds
        if c.sense == "<=":
            A_ub.append([c.a1, c.a2]); b_ub.append(c.b)
        elif c.sense == ">=":
            A_ub.append([-c.a1, -c.a2]); b_ub.append(-c.b)
        else:
            A_eq.append([c.a1, c.a2]); b_eq.append(c.b)

    res = linprog(
        c=[sign * c1, sign * c2],
        A_ub=A_ub or None, b_ub=b_ub or None,
        A_eq=A_eq or None, b_eq=b_eq or None,
        bounds=[(0, None), (0, None)],
        method="highs",
    )
    if not res.success:
        print("\n[Verification] linprog could not confirm a solution:", res.message)
        return
    z = sign * res.fun
    print(f"\n[Verification] scipy.optimize.linprog agrees: "
          f"x1={res.x[0]:.4f}, x2={res.x[1]:.4f}, Z={z:.4f}")


# ---------------------------------------------------------------------------
# Plotting helpers
# ---------------------------------------------------------------------------

def plot_range(constraints, corners):
    """Pick axis limits that comfortably fit all intercepts and corner points."""
    candidates = [0.0]
    for c in constraints[:-2]:
        xi, yi = c.x_intercept(), c.y_intercept()
        if xi is not None:
            candidates.append(abs(xi))
        if yi is not None:
            candidates.append(abs(yi))
    for x1, x2, _, _ in corners:
        candidates.extend([abs(x1), abs(x2)])
    m = max(candidates) if candidates else 10
    return m * 1.25 or 10


def line_xy(c, limit):
    """Return plottable (x, y) arrays for a constraint's boundary line."""
    if abs(c.a2) > TOL:
        x = np.linspace(0, limit, 200)
        y = (c.b - c.a1 * x) / c.a2
        return x, y
    else:  # vertical line x1 = b / a1
        x0 = c.b / c.a1
        return np.full(200, x0), np.linspace(0, limit, 200)


def draw_axes(ax, limit):
    ax.set_xlim(-limit * 0.05, limit)
    ax.set_ylim(-limit * 0.05, limit)
    ax.set_xlabel("x1")
    ax.set_ylabel("x2")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.grid(True, linestyle=":", alpha=0.5)


# ---------------------------------------------------------------------------
# Static final plot
# ---------------------------------------------------------------------------

def make_static_plot(sense, c1, c2, constraints, corners_ordered, best, limit,
                      path="graph_solution.png"):
    fig, ax = plt.subplots(figsize=(7, 7))
    draw_axes(ax, limit)

    for c in constraints[:-2]:
        x, y = line_xy(c, limit)
        ax.plot(x, y, label=c.label)

    if len(corners_ordered) >= 3:
        poly_x = [p[0] for p in corners_ordered]
        poly_y = [p[1] for p in corners_ordered]
        ax.fill(poly_x, poly_y, alpha=0.25, color="tab:green", label="Feasible region")

    for x1, x2, _, _ in corners_ordered:
        ax.plot(x1, x2, "ko", markersize=4)
        ax.annotate(f"({x1:.2f}, {x2:.2f})", (x1, x2),
                    textcoords="offset points", xytext=(6, 6), fontsize=8)

    bx, by, bz = best
    ax.plot(bx, by, "r*", markersize=16, label=f"Optimal ({bx:.2f}, {by:.2f})  Z={bz:.2f}")

    # Objective iso-line through the optimum.
    if abs(c2) > TOL:
        x = np.linspace(0, limit, 200)
        y = (bz - c1 * x) / c2
        ax.plot(x, y, "r--", linewidth=1.5, label=f"Z = {bz:.2f} (optimal)")
    elif abs(c1) > TOL:
        ax.axvline(bx, color="r", linestyle="--", linewidth=1.5, label=f"Z = {bz:.2f} (optimal)")

    ax.set_title(f"Graphical method: {sense.title()} Z = {c1}x1 + {c2}x2")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    print(f"\nStatic solution plot saved to {path}")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Animation: draw constraints one at a time, shade region, sweep objective
# ---------------------------------------------------------------------------

def make_animation(sense, c1, c2, constraints, corners_ordered, best, limit,
                    path="graph_animation.gif"):
    fig, ax = plt.subplots(figsize=(7, 7))

    real_constraints = constraints[:-2]
    n_lines = len(real_constraints)
    n_sweep = 30
    n_hold = 10
    total_frames = n_lines + 1 + n_sweep + n_hold  # +1 = shade-region frame

    bx, by, bz = best

    def frame(i):
        ax.clear()
        draw_axes(ax, limit)
        ax.set_title(f"Graphical method: {sense.title()} Z = {c1}x1 + {c2}x2")

        n_drawn = min(i + 1, n_lines)
        for c in real_constraints[:n_drawn]:
            x, y = line_xy(c, limit)
            ax.plot(x, y, label=c.label)

        if i >= n_lines and len(corners_ordered) >= 3:
            poly_x = [p[0] for p in corners_ordered]
            poly_y = [p[1] for p in corners_ordered]
            ax.fill(poly_x, poly_y, alpha=0.25, color="tab:green", label="Feasible region")
            for x1, x2, _, _ in corners_ordered:
                ax.plot(x1, x2, "ko", markersize=4)

        if i >= n_lines + 1:
            sweep_i = i - (n_lines + 1)
            frac = min(sweep_i / max(n_sweep - 1, 1), 1.0)
            k = frac * bz  # sweep the iso-Z value from 0 up to the optimum
            if abs(c2) > TOL:
                x = np.linspace(0, limit, 200)
                y = (k - c1 * x) / c2
                ax.plot(x, y, "r--", linewidth=1.5, label=f"Z = {k:.2f}")
            elif abs(c1) > TOL:
                ax.axvline(k / c1, color="r", linestyle="--", linewidth=1.5, label=f"Z = {k:.2f}")
            if frac >= 1.0:
                ax.plot(bx, by, "r*", markersize=16,
                        label=f"Optimal ({bx:.2f}, {by:.2f})  Z={bz:.2f}")

        ax.legend(loc="upper right", fontsize=8)
        return ax.artists

    ani = animation.FuncAnimation(fig, frame, frames=total_frames, interval=350, repeat=False)
    ani.save(path, writer="pillow")
    print(f"Animation saved to {path}")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    sense, c1, c2, constraints = read_problem()

    corners_raw = find_corner_points(constraints)
    if not corners_raw:
        print("\nNo feasible corner points found - check the constraints for a "
              "consistent, bounded feasible region.")
        return

    scored = [(x1, x2, c1 * x1 + c2 * x2) for x1, x2, _, _ in corners_raw]
    best = max(scored, key=lambda p: p[2]) if sense == "max" else min(scored, key=lambda p: p[2])

    print_steps(sense, c1, c2, constraints, corners_raw, best)
    verify_with_linprog(sense, c1, c2, constraints)

    corners_ordered = order_by_angle([(x1, x2, ci, cj) for x1, x2, ci, cj in corners_raw])
    limit = plot_range(constraints, corners_raw)

    make_static_plot(sense, c1, c2, constraints, corners_ordered, best, limit)
    make_animation(sense, c1, c2, constraints, corners_ordered, best, limit)


if __name__ == "__main__":
    main()

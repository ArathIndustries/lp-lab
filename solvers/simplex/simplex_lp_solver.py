"""
Step-by-step simplex method solver for linear programs (any number of variables).

Uses the ROW-0 (Z-row) tableau convention of Hillier & Lieberman: the
objective is rewritten as the equation

    Z - c1*x1 - c2*x2 - ... (+/- M*artificials) = 0

and carried as Row 0 of every tableau. The row-0 coefficients are the
(negated) reduced costs, so:
    maximization: enter the MOST NEGATIVE row-0 coefficient; optimal when
                  every row-0 coefficient is >= 0.
    minimization: enter the MOST POSITIVE row-0 coefficient; optimal when
                  every row-0 coefficient is <= 0.
(The older Cj/Zj/Cj-Zj layout found in Taha-style texts carries the same
numbers with opposite sign: row-0 coefficient = Zj - Cj = -(Cj - Zj).)

The program walks through the full textbook solution:

  1. Preprocessing        - fix negative right-hand sides.
  2. Standard form        - add slack / surplus / artificial variables,
                            explaining WHY each one is needed; write the
                            objective as Row 0; for Big-M, eliminate the
                            basic artificial variables from Row 0 so the
                            starting tableau is in proper form.
  3. Method selection     - ordinary simplex if every constraint is <=,
                            Big-M method if any >= or = constraint forces
                            artificial variables in.
  4. Iterations           - every tableau printed with Row 0 on top;
                            entering variable, ratio test, leaving variable,
                            pivot element, and explicit row operations
                            (including the Row 0 update) shown.
  5. Special cases        - unbounded, infeasible (artificial stuck in basis),
                            degeneracy, and alternate optimal solutions are
                            detected and explained.
  6. Final answer         - variable values, slack/surplus interpretation,
                            optimal Z, optional scipy cross-check.

All arithmetic uses exact fractions (3/2, not 1.5) and the Big-M penalty is
kept SYMBOLIC (Row 0 entries like "4M-3"), so every tableau matches what
you would write by hand.

Run with:  python simplex_lp_solver.py
Inputs accept integers, decimals, or fractions (e.g. 3, 2.5, 7/2).
Only the standard library is required; scipy (if installed) is used for an
optional cross-check of the final answer.
"""

from fractions import Fraction

MAX_ITERATIONS = 50


# ---------------------------------------------------------------------------
# Numbers that may carry a symbolic Big-M term:  value = m*M + c
# ---------------------------------------------------------------------------

class MNum:
    """A number of the form m*M + c, where M is an arbitrarily large positive
    penalty. Comparisons treat the M part as dominant, which is exactly how
    the Big-M method reasons about Row 0 entries."""

    __slots__ = ("m", "c")

    def __init__(self, c=0, m=0):
        self.c = Fraction(c)
        self.m = Fraction(m)

    @staticmethod
    def wrap(x):
        return x if isinstance(x, MNum) else MNum(x)

    def __add__(self, other):
        o = MNum.wrap(other)
        return MNum(self.c + o.c, self.m + o.m)

    def __sub__(self, other):
        o = MNum.wrap(other)
        return MNum(self.c - o.c, self.m - o.m)

    def __mul__(self, other):
        o = MNum.wrap(other)
        if self.m and o.m:
            raise ValueError("M^2 term should never appear in a simplex tableau")
        return MNum(self.c * o.c, self.m * o.c + o.m * self.c)

    def __neg__(self):
        return MNum(-self.c, -self.m)

    def __abs__(self):
        return -self if self < 0 else self

    def _key(self):
        return (self.m, self.c)

    def __eq__(self, other):
        return self._key() == MNum.wrap(other)._key()

    def __lt__(self, other):
        return self._key() < MNum.wrap(other)._key()

    def __le__(self, other):
        return self._key() <= MNum.wrap(other)._key()

    def __gt__(self, other):
        return self._key() > MNum.wrap(other)._key()

    def __ge__(self, other):
        return self._key() >= MNum.wrap(other)._key()

    def is_zero(self):
        return self.m == 0 and self.c == 0


def fmt(x):
    """Format a Fraction or MNum the way a textbook tableau would."""
    if not isinstance(x, MNum):
        return str(Fraction(x))
    m, c = x.m, x.c
    if m == 0:
        return str(c)
    if m == 1:
        m_txt = "M"
    elif m == -1:
        m_txt = "-M"
    else:
        m_txt = f"{m}M"
    if c == 0:
        return m_txt
    sign = "+" if c > 0 else "-"
    return f"{m_txt}{sign}{abs(c)}"


# ---------------------------------------------------------------------------
# Console input
# ---------------------------------------------------------------------------

def read_frac(prompt):
    while True:
        raw = input(prompt).strip()
        try:
            return Fraction(raw)
        except (ValueError, ZeroDivisionError):
            print("  Enter a number (integer, decimal, or fraction like 7/2).")


def read_int(prompt, minimum=1):
    while True:
        raw = input(prompt).strip()
        if raw.isdigit() and int(raw) >= minimum:
            return int(raw)
        print(f"  Enter a whole number >= {minimum}.")


def read_sense(prompt):
    while True:
        raw = input(prompt).strip()
        if raw in ("<=", ">=", "="):
            return raw
        print("  Enter one of: <=  >=  =")


def read_problem():
    print("=== Objective function ===")
    print("Z = c1*x1 + c2*x2 + ... + cn*xn")
    opt = ""
    while opt not in ("max", "min"):
        opt = input("Maximize or minimize? (max/min): ").strip().lower()
    n_vars = read_int("How many decision variables? ")
    c = [read_frac(f"c{j + 1} (coefficient of x{j + 1}): ") for j in range(n_vars)]

    print("\n=== Constraints ===")
    print("(x_j >= 0 for all variables is assumed - do not enter those.)")
    n_cons = read_int("How many constraints? ")
    rows, senses, rhs = [], [], []
    for i in range(1, n_cons + 1):
        print(f"\nConstraint {i}: a1*x1 + ... + an*xn (sense) b")
        rows.append([read_frac(f"  coefficient of x{j + 1}: ") for j in range(n_vars)])
        senses.append(read_sense("  sense (<=, >=, =): "))
        rhs.append(read_frac("  b (right-hand side): "))

    pause = input("\nPause after each step? (y/n): ").strip().lower().startswith("y")
    return opt, c, rows, senses, rhs, pause


# ---------------------------------------------------------------------------
# Pretty printing
# ---------------------------------------------------------------------------

def heading(title):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def term_str(coef, name, first):
    """Render one term of a linear expression, e.g. '- 3/2x2'."""
    if first:
        lead = "-" if coef < 0 else ""
    else:
        lead = " - " if coef < 0 else " + "
    mag = abs(coef)
    mag_txt = "" if mag == 1 else str(mag)
    return f"{lead}{mag_txt}{name}"


def mterm_str(coef, name, first):
    """Like term_str but for MNum coefficients (used in the Row 0 equation)."""
    if coef.is_zero():
        return ""
    if coef.m != 0 and coef.c != 0:
        # Mixed aM+b coefficient: show it in parentheses for clarity.
        lead = "" if first else " + "
        return f"{lead}({fmt(coef)}){name}"
    if coef.m != 0:
        mag = MNum(0, abs(coef.m))
        negative = coef.m < 0
    else:
        mag = MNum(abs(coef.c))
        negative = coef.c < 0
    if first:
        lead = "-" if negative else ""
    else:
        lead = " - " if negative else " + "
    mag_txt = "" if mag == MNum(1) or mag == MNum(0, 1) else fmt(mag)
    if mag == MNum(0, 1):
        mag_txt = "M"
        return f"{lead}{mag_txt}*{name}"
    return f"{lead}{mag_txt}{name}"


def expr_str(coefs, names):
    parts, first = [], True
    for coef, name in zip(coefs, names):
        if coef == 0:
            continue
        parts.append(term_str(coef, name, first))
        first = False
    return "".join(parts) if parts else "0"


def row0_equation_str(row0, rhs0, names):
    parts = []
    for coef, name in zip(row0, names):
        txt = mterm_str(coef, name, first=False)
        if txt:
            parts.append(txt)
    body = "".join(parts)
    return f"Z{body} = {fmt(rhs0)}"


def print_original(opt, c, rows, senses, rhs):
    heading("STEP 0 - THE PROBLEM AS GIVEN")
    names = [f"x{j + 1}" for j in range(len(c))]
    print(f"\n{opt.title()}imize  Z = {expr_str(c, names)}")
    print("subject to:")
    for row, s, b in zip(rows, senses, rhs):
        print(f"  {expr_str(row, names)} {s} {fmt(b)}")
    print(f"  {', '.join(names)} >= 0")


# ---------------------------------------------------------------------------
# Standard form: slacks, surpluses, artificials, and Row 0
# ---------------------------------------------------------------------------

class Tableau:
    def __init__(self):
        self.var_names = []    # column names, decision vars first
        self.var_kinds = []    # 'decision' | 'slack' | 'surplus' | 'artificial'
        self.rows = []         # constraint coefficients (Fraction)
        self.rhs = []          # right-hand sides (Fraction)
        self.basis = []        # column index of the basic variable in each row
        self.row0 = []         # Row 0 coefficients (MNum), one per column
        self.rhs0 = MNum(0)    # Row 0 right-hand side = current Z


def standardize(opt, c, rows, senses, rhs, big_m_sign):
    """Build the initial tableau in row-0 form, printing an explanation of
    every new variable and of the Row 0 setup."""
    n_vars = len(c)
    t = Tableau()
    t.var_names = [f"x{j + 1}" for j in range(n_vars)]
    t.var_kinds = ["decision"] * n_vars
    t.rows = [[Fraction(v) for v in row] for row in rows]
    t.rhs = [Fraction(b) for b in rhs]
    t.basis = [None] * len(rows)
    obj_coef = [MNum(cj) for cj in c]   # objective coefficient per column

    heading("STEP 2 - CONVERT TO STANDARD FORM")
    print("\nThe simplex method needs every constraint to be an EQUATION with a")
    print("non-negative right-hand side, and it needs an obvious starting basic")
    print("feasible solution (one basic variable per row). We add variables:")
    print("  <=  : add a SLACK variable      (unused capacity; starts basic)")
    print("  >=  : subtract a SURPLUS variable (amount above the minimum), but a")
    print("        surplus of -b is not allowed, so also add an ARTIFICIAL variable")
    print("  =   : no slack exists, so add an ARTIFICIAL variable to start from")
    print("Artificial variables are fake - they only exist to give a starting")
    print("basis, so the Big-M method charges them a huge penalty M in Z to force")
    print("them out of the solution.\n")

    n_slack = n_surplus = n_artificial = 0
    artificial_cols = []

    for i, s in enumerate(senses):
        added = []
        if s == "<=":
            n_slack += 1
            name = f"s{n_slack}"
            _add_column(t, obj_coef, name, "slack", MNum(0), i, Fraction(1))
            t.basis[i] = len(t.var_names) - 1
            added.append(f"+ {name} (slack, starts in the basis)")
        elif s == ">=":
            n_surplus += 1
            name = f"e{n_surplus}"
            _add_column(t, obj_coef, name, "surplus", MNum(0), i, Fraction(-1))
            added.append(f"- {name} (surplus)")
            n_artificial += 1
            aname = f"a{n_artificial}"
            _add_column(t, obj_coef, aname, "artificial",
                        MNum(0, big_m_sign), i, Fraction(1))
            col = len(t.var_names) - 1
            t.basis[i] = col
            artificial_cols.append(col)
            added.append(f"+ {aname} (artificial, starts in the basis)")
        else:  # '='
            n_artificial += 1
            aname = f"a{n_artificial}"
            _add_column(t, obj_coef, aname, "artificial",
                        MNum(0, big_m_sign), i, Fraction(1))
            col = len(t.var_names) - 1
            t.basis[i] = col
            artificial_cols.append(col)
            added.append(f"+ {aname} (artificial, starts in the basis)")
        print(f"  Constraint {i + 1} ({s}):  {'  '.join(added)}")

    names = t.var_names
    print("\nStandard form:")
    obj = expr_str([mn.c for mn in obj_coef[:n_vars]], names[:n_vars])
    if n_artificial:
        pen = " ".join(
            f"{'-' if big_m_sign < 0 else '+'} M*{t.var_names[col]}"
            for col in artificial_cols)
        direction = ("subtract M times each artificial (max problem)"
                     if big_m_sign < 0 else
                     "add M times each artificial (min problem)")
        print(f"  {opt.title()}imize  Z = {obj} {pen}")
        print(f"  (Big-M: {direction}, so any artificial left in the final")
        print("   solution would make Z catastrophically bad.)")
    else:
        print(f"  {opt.title()}imize  Z = {obj}")
    print("subject to:")
    for row, b in zip(t.rows, t.rhs):
        print(f"  {expr_str(row, names)} = {fmt(b)}")
    print("  all variables >= 0")

    # ----- Row 0: move every objective term to the left-hand side ---------
    print("\nWrite the objective as an EQUATION and move every variable term")
    print("to the left-hand side - this becomes Row 0 of the tableau:")
    t.row0 = [-cj for cj in obj_coef]
    t.rhs0 = MNum(0)
    print(f"  (R0)  {row0_equation_str(t.row0, t.rhs0, names)}")
    print("  (Notice the objective coefficients change sign when they cross")
    print("   the equals sign - this is where the -c values come from.)")

    print("\nStarting basic feasible solution (one basic variable per row):")
    for i, col in enumerate(t.basis):
        print(f"  Row {i + 1}: {t.var_names[col]} = {fmt(t.rhs[i])}")

    # ----- Proper form: basic variables must have coefficient 0 in Row 0 --
    fixups = [(i, col) for i, col in enumerate(t.basis)
              if not t.row0[col].is_zero()]
    if fixups:
        print("\nPROPER FORM CHECK: every BASIC variable must have a coefficient")
        print("of 0 in Row 0 (otherwise Z is not expressed purely in terms of")
        print("non-basic variables). The artificial variables are basic but")
        print(f"carry {'-M' if big_m_sign < 0 else '+M'} in the objective,"
              f" so their Row 0 entries are"
              f" {'+M' if big_m_sign < 0 else '-M'}, not 0.")
        print("Eliminate them with Gaussian row operations on Row 0:")
        for i, col in enumerate(t.basis):
            if t.row0[col].is_zero():
                continue
            factor = t.row0[col]
            sign = "-" if factor > 0 else "+"
            print(f"  New R0 = R0 {sign} ({fmt(abs(factor))}) * R{i + 1}"
                  f"    <- clears the {t.var_names[col]} entry")
            t.row0 = [v - factor * MNum(a) for v, a in zip(t.row0, t.rows[i])]
            t.rhs0 = t.rhs0 - factor * MNum(t.rhs[i])
        print(f"\n  (R0)  {row0_equation_str(t.row0, t.rhs0, names)}")
        print("  Row 0's RHS now equals Z at the starting solution"
              f" (Z = {fmt(t.rhs0)}).")

    return t, artificial_cols


def _add_column(t, obj_coef, name, kind, cj, row_index, value):
    """Append a new column that is `value` in one row and 0 elsewhere."""
    t.var_names.append(name)
    t.var_kinds.append(kind)
    obj_coef.append(cj)
    for r, row in enumerate(t.rows):
        row.append(value if r == row_index else Fraction(0))


# ---------------------------------------------------------------------------
# Tableau display (row-0 form)
# ---------------------------------------------------------------------------

def print_tableau(t, title, ratios=None, pivot=None):
    """ratios: list aligned with constraint rows (string or None).
    pivot: (row, col) within the constraint rows."""
    cells = []
    header = ["Row", "Basis", "Z"] + t.var_names + ["RHS"]
    if ratios is not None:
        header.append("Ratio")
    cells.append(header)

    r0 = ["R0", "Z", "1"] + [fmt(v) for v in t.row0] + [fmt(t.rhs0)]
    if ratios is not None:
        r0.append("")
    cells.append(r0)

    for i, row in enumerate(t.rows):
        body = []
        for j, v in enumerate(row):
            txt = fmt(v)
            if pivot and pivot == (i, j):
                txt = f"[{txt}]"
            body.append(txt)
        line = ([f"R{i + 1}", t.var_names[t.basis[i]], "0"]
                + body + [fmt(t.rhs[i])])
        if ratios is not None:
            line.append(ratios[i] if ratios[i] is not None else "-")
        cells.append(line)

    widths = [max(len(r[k]) for r in cells) for k in range(len(cells[0]))]
    print(f"\n{title}")
    for idx, r in enumerate(cells):
        print("  " + " | ".join(v.rjust(w) for v, w in zip(r, widths)))
        if idx in (0, 1):  # under the header and under Row 0
            print("  " + "-+-".join("-" * w for w in widths))


# ---------------------------------------------------------------------------
# The simplex iterations
# ---------------------------------------------------------------------------

def choose_entering(t, opt):
    """Max: most NEGATIVE Row 0 coefficient (raising that variable increases
    Z the fastest). Min: most POSITIVE (raising it decreases Z the fastest).
    Ties -> lowest index (Bland's rule) to guard against cycling."""
    best_j, best_val = None, MNum(0)
    for j, v in enumerate(t.row0):
        if opt == "max" and v < best_val:
            best_j, best_val = j, v
        elif opt == "min" and v > best_val:
            best_j, best_val = j, v
    return best_j, best_val


def ratio_test(t, col):
    """Minimum ratio RHS/a for rows with a > 0. Returns (row, ratio, strings)."""
    best_i, best_ratio = None, None
    strings = []
    for i, row in enumerate(t.rows):
        a = row[col]
        if a > 0:
            ratio = t.rhs[i] / a
            b_txt = fmt(t.rhs[i])
            a_txt = fmt(a)
            if "/" in b_txt:
                b_txt = f"({b_txt})"
            if "/" in a_txt:
                a_txt = f"({a_txt})"
            strings.append(f"{b_txt}/{a_txt} = {fmt(ratio)}")
            if best_ratio is None or ratio < best_ratio:
                best_i, best_ratio = i, ratio
        else:
            strings.append(None)
    return best_i, best_ratio, strings


def pivot_explain(t, prow, pcol):
    """Perform the pivot, printing every row operation including Row 0."""
    p = t.rows[prow][pcol]
    print(f"\n  Row operations (pivot element = {fmt(p)}):")
    if p != 1:
        print(f"    New R{prow + 1} = R{prow + 1} / ({fmt(p)})"
              f"          <- make the pivot element 1")
    else:
        print(f"    New R{prow + 1} = R{prow + 1}"
              f"                 <- pivot element is already 1")
    t.rows[prow] = [v / p for v in t.rows[prow]]
    t.rhs[prow] = t.rhs[prow] / p

    # Row 0 first (that is how it is usually written on paper).
    factor0 = t.row0[pcol]
    if factor0.is_zero():
        print("    New R0 = R0                 <- already 0 in the pivot column")
    else:
        sign = "-" if factor0 > 0 else "+"
        print(f"    New R0 = R0 {sign} ({fmt(abs(factor0))}) * New R{prow + 1}"
              f"  <- clear the pivot column in Row 0")
        t.row0 = [v - factor0 * MNum(a)
                  for v, a in zip(t.row0, t.rows[prow])]
        t.rhs0 = t.rhs0 - factor0 * MNum(t.rhs[prow])

    for i in range(len(t.rows)):
        if i == prow:
            continue
        factor = t.rows[i][pcol]
        if factor == 0:
            print(f"    New R{i + 1} = R{i + 1}"
                  f"                 <- already 0 in the pivot column")
            continue
        sign = "-" if factor > 0 else "+"
        print(f"    New R{i + 1} = R{i + 1} {sign} ({fmt(abs(factor))}) * New R{prow + 1}"
              f"  <- clear the pivot column")
        t.rows[i] = [v - factor * pv for v, pv in zip(t.rows[i], t.rows[prow])]
        t.rhs[i] = t.rhs[i] - factor * t.rhs[prow]

    t.basis[prow] = pcol


def wait(pause):
    if pause:
        input("\n  ... press Enter to continue ...")


def run_simplex(t, opt, artificial_cols, pause):
    heading("STEP 3 - SIMPLEX ITERATIONS")
    print("\nRow 0 reads  Z + (coeffs)*(variables) = RHS,  i.e.")
    print("  Z = RHS - (coeff_j)*x_j for each non-basic variable x_j.")
    if opt == "max":
        print("So a NEGATIVE Row 0 coefficient means raising that variable")
        print("INCREASES Z. Rule (maximization): the ENTERING variable has the")
        print("MOST NEGATIVE Row 0 coefficient; optimal when all are >= 0.")
    else:
        print("So a POSITIVE Row 0 coefficient means raising that variable")
        print("DECREASES Z. Rule (minimization): the ENTERING variable has the")
        print("MOST POSITIVE Row 0 coefficient; optimal when all are <= 0.")
    print("The LEAVING variable comes from the minimum-ratio test: among rows")
    print("with a POSITIVE entry in the pivot column, the smallest RHS/entry")
    print("ratio leaves - going any further would drive a basic variable")
    print("negative and exit the feasible region.")

    iteration = 0
    while True:
        iteration += 1
        if iteration > MAX_ITERATIONS:
            print(f"\nStopped after {MAX_ITERATIONS} iterations - possible cycling.")
            return "stalled"

        print_tableau(t, f"\n--- Tableau {iteration} ---")

        degenerate = [t.var_names[t.basis[i]]
                      for i in range(len(t.rows)) if t.rhs[i] == 0]
        if degenerate:
            print(f"\n  Note: DEGENERACY - basic variable(s) {', '.join(degenerate)}")
            print("  equal 0. The method still works; some pivots may not improve Z.")

        entering, best_val = choose_entering(t, opt)
        if entering is None:
            print(f"\n  Every Row 0 coefficient is"
                  f" {'>= 0' if opt == 'max' else '<= 0'}"
                  f"  =>  this tableau is OPTIMAL.")
            return "optimal"

        goal = "increase" if opt == "max" else "decrease"
        print(f"\n  Entering variable: {t.var_names[entering]}"
              f"  (Row 0 coefficient = {fmt(best_val)},"
              f" the best rate of {goal} in Z)")

        prow, best_ratio, ratio_strings = ratio_test(t, entering)
        if prow is None:
            print(f"\n  No entry in the {t.var_names[entering]} column is positive,")
            print(f"  so {t.var_names[entering]} can grow forever without any basic")
            print("  variable hitting 0  =>  the problem is UNBOUNDED.")
            return "unbounded"

        print("\n  Minimum-ratio test (RHS / positive pivot-column entry):")
        for i, s in enumerate(ratio_strings):
            mark = "   <- minimum (leaves)" if i == prow else ""
            basic = t.var_names[t.basis[i]]
            print(f"    Row {i + 1} ({basic}): {s if s else 'entry <= 0, skip'}{mark}")
        ties = sum(1 for i, row in enumerate(t.rows)
                   if row[entering] > 0 and t.rhs[i] / row[entering] == best_ratio)
        if ties > 1:
            print("  Tie in the ratio test -> the next tableau will be degenerate;")
            print("  we break the tie by taking the topmost row.")

        print(f"\n  Leaving variable: {t.var_names[t.basis[prow]]}"
              f"  |  Pivot element: row {prow + 1}, column {t.var_names[entering]}"
              f" = {fmt(t.rows[prow][entering])}")
        print_tableau(t, f"  Tableau {iteration} with pivot marked [ ]:",
                      ratios=ratio_strings, pivot=(prow, entering))

        pivot_explain(t, prow, entering)
        wait(pause)


# ---------------------------------------------------------------------------
# Final reporting
# ---------------------------------------------------------------------------

def report_solution(t, opt, status):
    heading("STEP 4 - READ OFF THE SOLUTION")

    if status == "unbounded":
        print("\nRESULT: UNBOUNDED. The feasible region extends forever in the")
        print("direction that improves Z, so no finite optimum exists. (Check")
        print("whether a constraint was entered with the wrong sense.)")
        return
    if status == "stalled":
        print("\nRESULT: iteration limit reached without convergence.")
        return

    artificial_cols = {j for j, k in enumerate(t.var_kinds) if k == "artificial"}

    # Infeasibility: an artificial variable is basic at a positive value.
    for i, col in enumerate(t.basis):
        if col in artificial_cols and t.rhs[i] > 0:
            print(f"\nRESULT: INFEASIBLE. Artificial variable {t.var_names[col]}")
            print(f"is still in the basis at value {fmt(t.rhs[i])} even at the")
            print("'optimum'. Since artificials only exist to fake a starting")
            print("point, no real solution satisfies all constraints at once.")
            return

    values = {name: Fraction(0) for name in t.var_names}
    for i, col in enumerate(t.basis):
        values[t.var_names[col]] = t.rhs[i]

    n_dec = sum(1 for k in t.var_kinds if k == "decision")

    print("\nBasic variables take their RHS value; every non-basic variable = 0.")
    print("\nDecision variables:")
    for j in range(n_dec):
        print(f"  {t.var_names[j]} = {fmt(values[t.var_names[j]])}")
    print(f"\nOptimal objective value (Row 0's RHS):  Z = {fmt(t.rhs0)}")

    slack_like = [(j, t.var_names[j], t.var_kinds[j])
                  for j in range(len(t.var_names))
                  if t.var_kinds[j] in ("slack", "surplus")]
    if slack_like:
        print("\nSlack / surplus interpretation:")
        for j, name, kind in slack_like:
            v = values[name]
            if kind == "slack":
                note = ("constraint is BINDING (no room left)" if v == 0
                        else f"constraint has {fmt(v)} unit(s) of unused capacity")
            else:
                note = ("constraint is met exactly" if v == 0
                        else f"requirement exceeded by {fmt(v)} unit(s)")
            print(f"  {name} = {fmt(v)}  ->  {note}")

    # Alternate optima: a non-basic, non-artificial column with Row 0 coeff 0.
    basic_set = set(t.basis)
    alternates = [t.var_names[j] for j in range(len(t.var_names))
                  if j not in basic_set and j not in artificial_cols
                  and t.row0[j].is_zero()]
    if alternates:
        print(f"\nNote: ALTERNATE OPTIMA exist - non-basic variable(s)"
              f" {', '.join(alternates)} have a Row 0 coefficient of 0, so")
        print("pivoting them in gives a different corner point with the SAME Z.")

    return {t.var_names[j]: values[t.var_names[j]] for j in range(n_dec)}


def verify_with_scipy(opt, c, rows, senses, rhs, n_dec):
    try:
        from scipy.optimize import linprog
    except ImportError:
        print("\n[Verification] scipy not installed - skipping cross-check.")
        return
    sign = -1 if opt == "max" else 1
    A_ub, b_ub, A_eq, b_eq = [], [], [], []
    for row, s, b in zip(rows, senses, rhs):
        if s == "<=":
            A_ub.append([float(v) for v in row]); b_ub.append(float(b))
        elif s == ">=":
            A_ub.append([-float(v) for v in row]); b_ub.append(-float(b))
        else:
            A_eq.append([float(v) for v in row]); b_eq.append(float(b))
    res = linprog(c=[sign * float(v) for v in c],
                  A_ub=A_ub or None, b_ub=b_ub or None,
                  A_eq=A_eq or None, b_eq=b_eq or None,
                  bounds=[(0, None)] * n_dec, method="highs")
    if res.success:
        xs = ", ".join(f"x{j + 1}={v:.4f}" for j, v in enumerate(res.x))
        print(f"\n[Verification] scipy.optimize.linprog agrees: {xs},"
              f" Z={sign * res.fun:.4f}")
    else:
        print(f"\n[Verification] linprog status: {res.message}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    opt, c, rows, senses, rhs, pause = read_problem()
    print_original(opt, c, rows, senses, rhs)

    heading("STEP 1 - PREPROCESSING (right-hand sides must be >= 0)")
    fixed_any = False
    flip = {"<=": ">=", ">=": "<=", "=": "="}
    for i in range(len(rows)):
        if rhs[i] < 0:
            fixed_any = True
            print(f"\n  Constraint {i + 1} has b = {fmt(rhs[i])} < 0.")
            print("  Multiply the whole constraint by -1 (this FLIPS the sense):")
            rows[i] = [-v for v in rows[i]]
            rhs[i] = -rhs[i]
            senses[i] = flip[senses[i]]
            names = [f"x{j + 1}" for j in range(len(c))]
            print(f"    -> {expr_str(rows[i], names)} {senses[i]} {fmt(rhs[i])}")
    if not fixed_any:
        print("\n  All right-hand sides are already >= 0 - nothing to do.")

    needs_big_m = any(s in (">=", "=") for s in senses)
    big_m_sign = -1 if opt == "max" else 1
    print("\nMethod selection:")
    if needs_big_m:
        print("  At least one >= or = constraint exists, so slack variables alone")
        print("  cannot provide a starting basis  =>  use the BIG-M METHOD.")
    else:
        print("  Every constraint is <=, so the slack variables give a ready-made")
        print("  starting basis  =>  ordinary (standard) SIMPLEX METHOD.")
    wait(pause)

    t, artificial_cols = standardize(opt, c, rows, senses, rhs, big_m_sign)
    wait(pause)

    status = run_simplex(t, opt, artificial_cols, pause)
    result = report_solution(t, opt, status)

    if status == "optimal" and result is not None:
        verify_with_scipy(opt, c, rows, senses, rhs, len(c))


if __name__ == "__main__":
    main()

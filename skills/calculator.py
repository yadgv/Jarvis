"""An exact calculator with units, so sums aren't left to a language model's
guesswork: "what's 3.2 kN times 45 mm", "convert 350 kelvin to Fahrenheit",
"2.5 kW for 3 hours in kWh", "sqrt(2) * sin(30 deg)", "1 atm in psi".

Numbers, + - * / ^, brackets, functions (sqrt, sin, cos, tan, asin, acos,
atan, ln, log, log10, exp, abs, round), constants (pi, e, g, c, R, k_B,
N_A, h, sigma) and SI units with prefixes. "X to Y" / "X in Y" converts.
Nothing is ever run as code: the expression is parsed and walked by hand.
"""
import ast
import math
import re

DIMS = 7   # m, kg, s, A, K, mol, cd
_BASE = {"m": 0, "kg": 1, "s": 2, "A": 3, "K": 4, "mol": 5, "cd": 6}


def _d(**p):
    v = [0] * DIMS
    for k, n in p.items():
        v[_BASE[k]] = n
    return tuple(v)


NONE = _d()
L, M, T, I, TH = _d(m=1), _d(kg=1), _d(s=1), _d(A=1), _d(K=1)
FORCE = _d(kg=1, m=1, s=-2)
ENERGY = _d(kg=1, m=2, s=-2)
POWER = _d(kg=1, m=2, s=-3)
PRESSURE = _d(kg=1, m=-1, s=-2)
VOLT = _d(kg=1, m=2, s=-3, A=-1)


class Q:
    """A number with dimensions (SI)."""
    __slots__ = ("v", "d")

    def __init__(self, v, d=NONE):
        self.v, self.d = float(v), tuple(d)

    def _other(self, o):
        return o if isinstance(o, Q) else Q(o)

    def __add__(self, o):
        o = self._other(o)
        if o.d != self.d:
            raise ValueError(f"can't add {unit_name(self.d)} and {unit_name(o.d)}")
        return Q(self.v + o.v, self.d)

    def __sub__(self, o):
        return self + Q(-self._other(o).v, self._other(o).d)

    def __mul__(self, o):
        o = self._other(o)
        return Q(self.v * o.v, tuple(a + b for a, b in zip(self.d, o.d)))

    def __truediv__(self, o):
        o = self._other(o)
        if o.v == 0:
            raise ValueError("division by zero")
        return Q(self.v / o.v, tuple(a - b for a, b in zip(self.d, o.d)))

    def __pow__(self, o):
        o = self._other(o)
        if o.d != NONE:
            raise ValueError("a power must be a plain number")
        if abs(o.v) > 1000 or (self.d == NONE and abs(self.v) > 1 and abs(o.v) * math.log10(abs(self.v)) > 300):
            raise ValueError("that number is too big")
        return Q(self.v ** o.v, tuple(a * o.v for a in self.d))

    def __neg__(self):
        return Q(-self.v, self.d)


PREFIX = {"G": 1e9, "M": 1e6, "k": 1e3, "c": 1e-2, "m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12}
# unit -> (factor to SI, dims, takes SI prefixes)
UNITS = {
    "m": (1, L, True), "inch": (0.0254, L, False), "ft": (0.3048, L, False), "yd": (0.9144, L, False),
    "mi": (1609.344, L, False), "mile": (1609.344, L, False),
    "g": (1e-3, M, True), "t": (1000, M, False), "tonne": (1000, M, False), "lb": (0.45359237, M, False),
    "lbm": (0.45359237, M, False), "oz": (0.028349523, M, False),
    "s": (1, T, True), "min": (60, T, False), "h": (3600, T, False), "hr": (3600, T, False),
    "hour": (3600, T, False), "hours": (3600, T, False), "day": (86400, T, False), "days": (86400, T, False),
    "N": (1, FORCE, True), "lbf": (4.4482216, FORCE, False),
    "Pa": (1, PRESSURE, True), "bar": (1e5, PRESSURE, True), "atm": (101325, PRESSURE, False),
    "psi": (6894.757, PRESSURE, False), "ksi": (6894757, PRESSURE, False),
    "J": (1, ENERGY, True), "Wh": (3600, ENERGY, True), "cal": (4.184, ENERGY, True),
    "BTU": (1055.056, ENERGY, False), "eV": (1.602176634e-19, ENERGY, True),
    "W": (1, POWER, True), "hp": (745.69987, POWER, False),
    "V": (1, VOLT, True), "A": (1, I, True), "ohm": (1, _d(kg=1, m=2, s=-3, A=-2), True),
    "F": (1, _d(kg=-1, m=-2, s=4, A=2), True), "H": (1, _d(kg=1, m=2, s=-2, A=-2), True),
    "coulomb": (1, _d(A=1, s=1), False), "Hz": (1, _d(s=-1), True), "rpm": (1 / 60, _d(s=-1), False),
    "K": (1, TH, False), "mol": (1, _d(mol=1), True), "L": (1e-3, _d(m=3), True),
    "deg": (math.pi / 180, NONE, False), "rad": (1, NONE, False), "percent": (0.01, NONE, False),
}
CONSTANTS = {
    "pi": Q(math.pi), "e": Q(math.e), "g0": Q(9.80665, _d(m=1, s=-2)), "c0": Q(299792458, _d(m=1, s=-1)),
    "R": Q(8.314462618, _d(kg=1, m=2, s=-2, K=-1, mol=-1)), "k_B": Q(1.380649e-23, _d(kg=1, m=2, s=-2, K=-1)),
    "N_A": Q(6.02214076e23, _d(mol=-1)), "h_P": Q(6.62607015e-34, _d(kg=1, m=2, s=-1)),
    "sigma": Q(5.670374419e-8, _d(kg=1, s=-3, K=-4)),
}
FUNCS = {"sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan, "asin": math.asin,
         "acos": math.acos, "atan": math.atan, "ln": math.log, "log": math.log10, "log10": math.log10,
         "exp": math.exp, "abs": abs, "round": round}
NAMED = {(1, 0, -2, 0, 0, 0, 0): "N", ENERGY: "J", POWER: "W", PRESSURE: "Pa", VOLT: "V",
         _d(kg=1, m=1, s=-2): "N"}
NAMED[FORCE] = "N"
NAMED.update({UNITS["ohm"][1]: "Ω", UNITS["F"][1]: "F", UNITS["H"][1]: "H", UNITS["Hz"][1]: "Hz",
              _d(A=1, s=1): "C"})


def lookup(name):
    if name in CONSTANTS:
        return CONSTANTS[name]
    if name in UNITS:
        f, d, _ = UNITS[name]
        return Q(f, d)
    for p, scale in PREFIX.items():
        rest = name[len(p):]
        if name.startswith(p) and rest in UNITS and UNITS[rest][2]:
            f, d, _ = UNITS[rest]
            return Q(f * scale, d)
    raise ValueError(f"unknown unit or name '{name}'")


def _tidy(text):
    t = text.strip()
    for a, b in (("×", "*"), ("·", "*"), ("÷", "/"), ("^", "**"), ("²", "**2"), ("³", "**3"), ("µ", "u"),
                 ("μ", "u"), ("Ω", "ohm"), ("°", "deg"), ("−", "-"), ("%", " percent")):
        t = t.replace(a, b)
    words = {r"\btimes\b": "*", r"\bdivided by\b": "/", r"\bover\b": "/", r"\bplus\b": "+", r"\bminus\b": "-",
             r"\bsquared\b": "**2", r"\bcubed\b": "**3", r"\bto the power of\b": "**", r"\bper\b": "/",
             r"\bmultiplied by\b": "*", r"\bdegrees?\b": "deg", r"\bohms?\b": "ohm", r"\binches\b": "inch",
             r"\bfeet\b": "ft", r"\bfoot\b": "ft", r"\bseconds?\b": "s", r"\bminutes?\b": "min",
             r"\bmeters?\b|\bmetres?\b": "m", r"\bkilograms?\b": "kg", r"\bnewtons?\b": "N",
             r"\bpounds?\b": "lb", r"\bwatts?\b": "W", r"\bjoules?\b": "J", r"\bvolts?\b": "V", r"\bamps?\b": "A"}
    for pat, rep in words.items():
        t = re.sub(pat, rep, t, flags=re.I)
    t = re.sub(r"(?<=\d)\s*in\b(?=\s*$|\s*[*/)])", " inch", t)     # "12 in" is inches...
    t = re.sub(r"\bdeg\s*([CF])\b", r"deg\1", t)
    t = t.replace(",", "")
    t = re.sub(r"(\d)[eE]([-+]?\d+)", r"\1*10**(\2)", t)   # 1.5e-3 -> 1.5*10**(-3)
    # "3.2 kN" is one quantity: (3.2*kN), so "100 km / 2 h" is (100 km)/(2 h)
    t = re.sub(r"(?<![\w.])(\d+\.?\d*(?:[eE][-+]?\d+)?)\s*([A-Za-z_]\w*(?:\*\*-?\d+)?)(?!\s*\()",
               lambda m: f"({m.group(1)}*{m.group(2)})" if m.group(2) not in FUNCS else m.group(0), t)
    t = re.sub(r"\)\s+\(", ")+(", t)          # "5 ft 3 inch", "1 h 30 min": add them up
    # 2(3) -> 2*(3) ;  kN m -> kN*m
    t = re.sub(r"(\d|\))\s*(?=[A-Za-z_(])", r"\1*", t)
    t = re.sub(r"([A-Za-z_]\w*)\s+(?=[A-Za-z_(])", lambda m: m.group(1) + ("*" if m.group(1) not in FUNCS else ""), t)
    return t


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return Q(node.value)
    if isinstance(node, ast.Name):
        return lookup(node.id)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = _eval(node.operand)
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.BinOp):
        a, b = _eval(node.left), _eval(node.right)
        ops = {ast.Add: Q.__add__, ast.Sub: Q.__sub__, ast.Mult: Q.__mul__, ast.Div: Q.__truediv__,
               ast.Pow: Q.__pow__}
        if type(node.op) not in ops:
            raise ValueError("only + - * / and powers")
        return ops[type(node.op)](a, b)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCS and len(node.args) == 1:
        x = _eval(node.args[0])
        if x.d != NONE:
            raise ValueError(f"{node.func.id} needs a plain number")
        try:
            return Q(FUNCS[node.func.id](x.v))
        except (ValueError, OverflowError) as e:
            raise ValueError(f"{node.func.id}: {e}")
    raise ValueError("I can only do arithmetic, functions and units")


def evaluate(text) -> Q:
    t = _tidy(text)
    if len(t) > 300:
        raise ValueError("that's too long")
    return _eval(ast.parse(t, mode="eval"))


def unit_name(d):
    if d == NONE:
        return ""
    if d in NAMED:
        return NAMED[d]
    names = list(_BASE)
    top = [f"{n}^{p:g}" if p != 1 else n for n, p in zip(names, d) if p > 0]
    bottom = [f"{n}^{-p:g}" if p != -1 else n for n, p in zip(names, d) if p < 0]
    under = ("(" + "·".join(bottom) + ")") if len(bottom) > 1 else "·".join(bottom)
    return "·".join(top) + ("/" + under if bottom else "") if top else "1/" + under


def fmt(v):
    if v == 0:
        return "0"
    if 1e-4 <= abs(v) < 1e7:
        return f"{v:.6g}"
    return f"{v:.4e}".replace("e+0", "e").replace("e+", "e").replace("e-0", "e-")


TEMP = {"c": "C", "celsius": "C", "degc": "C", "f": "F", "fahrenheit": "F", "degf": "F", "k": "K", "kelvin": "K"}
_TEMP = re.compile(r"^\s*(-?[\d.]+)\s*(?:°|deg(?:rees?)?\s*)?(celsius|fahrenheit|kelvin|degc|degf|[cfk])\s+"
                   r"(?:to|in|into)\s+(?:°|deg(?:rees?)?\s*)?(celsius|fahrenheit|kelvin|degc|degf|[cfk])\s*$", re.I)


def _temperature(text):
    m = _TEMP.match(text)
    if not m:
        return None
    v, a, b = float(m.group(1)), TEMP[m.group(2).lower()], TEMP[m.group(3).lower()]
    k = {"C": v + 273.15, "F": (v - 32) * 5 / 9 + 273.15, "K": v}[a]
    out = {"C": k - 273.15, "F": (k - 273.15) * 9 / 5 + 32, "K": k}[b]
    return f"{fmt(v)} °{a} = {fmt(out)} °{b}".replace("°K", "K")


def calculate(a):
    text = str(a.get("expression") or "").strip()
    if not text:
        return "What should I work out?"
    temp = _temperature(text)
    if temp:
        return temp
    target = None
    m = re.match(r"^(.*\S)\s+(?:to|in|into|as)\s+([A-Za-z°µμΩ][\w°µμΩ/*^.\s]*)$", text)
    if m:
        target = m.group(2).strip()
        text = m.group(1)
    try:
        q = evaluate(text)
        if target:
            u = evaluate(target)
            if u.d != q.d:
                return f"Can't convert {unit_name(q.d) or 'a plain number'} to {target}."
            return f"{fmt(q.v / u.v)} {target}"
        if q.d == NONE:
            return fmt(q.v)
        return f"{fmt(q.v)} {unit_name(q.d)}"
    except ZeroDivisionError:
        return "That divides by zero."
    except (ValueError, SyntaxError, TypeError, OverflowError) as e:
        return f"Couldn't work that out ({e}). Say it as a plain sum, e.g. '3.2 kN * 45 mm in N m'."


SKILLS = [
    {
        "name": "calculate",
        "description": "Exact maths with units: arithmetic, sqrt/sin/log, constants (pi, g0, R), unit "
                       "conversions ('3.2 kN * 45 mm in N m', '1 atm in psi', '350 K to F'). Use it for any "
                       "number he asks you to work out instead of doing it in your head.",
        "parameters": {"type": "object", "properties": {
            "expression": {"type": "string", "description": "e.g. '2.5 kW * 3 h in kWh' or 'sqrt(2)*sin(30 deg)'"}},
            "required": ["expression"]},
        "run": calculate,
    },
]

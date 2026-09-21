"""AST back to formula text. Names are quoted when they contain anything
outside [A-Za-z0-9_ ] or begin with a digit or equal a keyword, which is a
superset of Anapedia's rule (quote when the name contains a number, an
operator, or the words IF AND OR). Fully parenthesises binary operators,
so the output is unambiguous even if the input relied on precedence."""
from .functions import KEYWORDS, CLAUSE_KINDS, FUNCTIONS
import re

_SAFE = re.compile(r"^[A-Za-z_][A-Za-z0-9_ ]*$")


def _name(s: str) -> str:
    up = s.upper()
    if _SAFE.match(s) and up not in KEYWORDS and up not in CLAUSE_KINDS and not any(
        w.upper() in KEYWORDS or w.upper() in CLAUSE_KINDS for w in s.split()
    ) and up not in FUNCTIONS:
        return s
    return "'" + s.replace("'", "''") + "'"


def unparse(n) -> str:
    t = n["t"]
    if t == "num": return n["v"]
    if t == "str": return '"' + n["v"] + '"'
    if t == "bool": return "TRUE" if n["v"] else "FALSE"
    if t == "blank": return "BLANK"
    if t == "ref": return ".".join(_name(p) for p in n["path"])
    if t == "un": return ("NOT " if n["op"] == "NOT" else "-") + unparse(n["x"])
    if t == "bin":
        # Left-associative chains (a + b + c + ... hundreds deep in real models)
        # are flattened iteratively to avoid recursion limits.
        op = n["op"]
        parts = []
        cur = n
        while isinstance(cur, dict) and cur.get("t") == "bin" and cur["op"] == op:
            parts.append(cur["r"])
            cur = cur["l"]
        parts.append(cur)
        parts.reverse()
        return "(" + (" " + op + " ").join(unparse(x) for x in parts) + ")"
    if t == "if":
        if n.get("form") == "spreadsheet":
            return "IF(" + unparse(n["c"]) + ", " + unparse(n["a"]) + ", " + unparse(n["b"]) + ")"
        # parenthesised: an IF inside a larger expression would otherwise swallow the tail into ELSE
        return "(IF " + unparse(n["c"]) + " THEN " + unparse(n["a"]) + " ELSE " + unparse(n["b"]) + ")"
    if t == "call": return n["f"] + "(" + ", ".join(unparse(a) for a in n["args"]) + ")"
    if t == "kwarg": return n["v"]
    if t == "clause":
        return unparse(n["x"]) + "[" + ", ".join(c["k"] + ": " + unparse(c["m"]) for c in n["clauses"]) + "]"
    raise ValueError(t)

"""Recursive-descent parser for Anaplan formulas, producing a small AST.

AST node shapes (dicts, for JSON-friendliness):
  {"t":"num","v":"1.5"} {"t":"str","v":"x"} {"t":"bool","v":True} {"t":"blank"}
  {"t":"ref","path":["Module","Line Item"]}
  {"t":"bin","op":"+","l":...,"r":...}  {"t":"un","op":"NOT"|"-","x":...}
  {"t":"if","c":...,"a":...,"b":...}
  {"t":"call","f":"SUM","args":[...]}  {"t":"kwarg","v":"ASCENDING"}
  {"t":"clause","x":<expr>,"clauses":[{"k":"SUM","m":<expr>}, ...]}
"""
from __future__ import annotations
from .lexer import tokenize, Tok, LexError
from .functions import CLAUSE_KINDS, KEYWORD_ARGS


class ParseError(Exception):
    def __init__(self, msg, tok: Tok):
        super().__init__(f"{msg} at {tok.pos} (got {tok.kind} {tok.text!r})")
        self.pos = tok.pos
        self.tok = tok


class Parser:
    def __init__(self, s: str):
        self.s = s
        self.toks = tokenize(s)
        self.i = 0

    @property
    def cur(self) -> Tok:
        return self.toks[self.i]

    def peek(self, k=1) -> Tok:
        return self.toks[min(self.i + k, len(self.toks) - 1)]

    def eat(self, kind, text=None) -> Tok:
        t = self.cur
        if t.kind != kind or (text is not None and t.text != text):
            raise ParseError(f"expected {kind} {text or ''}".strip(), t)
        self.i += 1
        return t

    def at(self, kind, text=None) -> bool:
        t = self.cur
        return t.kind == kind and (text is None or t.text == text)

    # ---- grammar ----
    def parse(self):
        node = self.expression()
        if not self.at("EOF"):
            raise ParseError("trailing input", self.cur)
        return node

    def expression(self):
        return self.or_expr()

    def _binary(self, sub, ops, kind="OP"):
        left = sub()
        while any(self.at(kind, o) for o in ops):
            op = self.cur.text
            self.i += 1
            right = sub()
            left = {"t": "bin", "op": op, "l": left, "r": right}
        return left

    def or_expr(self):
        return self._binary(self.and_expr, ["OR"], "KW")

    def and_expr(self):
        return self._binary(self.eq_expr, ["AND"], "KW")

    def eq_expr(self):
        return self._binary(self.rel_expr, ["=", "<>"])

    def rel_expr(self):
        return self._binary(self.concat_expr, ["<", "<=", ">", ">="])

    def concat_expr(self):
        return self._binary(self.add_expr, ["&"])

    def add_expr(self):
        return self._binary(self.mul_expr, ["+", "-"])

    def mul_expr(self):
        return self._binary(self.unary, ["*", "/"])

    def unary(self):
        if self.at("KW", "NOT"):
            self.i += 1
            return {"t": "un", "op": "NOT", "x": self.unary()}
        if self.at("OP", "-"):
            self.i += 1
            return {"t": "un", "op": "-", "x": self.unary()}
        return self.postfix()

    def postfix(self):
        node = self.primary()
        while self.at("OP", "["):
            self.i += 1
            clauses = [self.clause()]
            while self.at("OP", ","):
                self.i += 1
                clauses.append(self.clause())
            self.eat("OP", "]")
            node = {"t": "clause", "x": node, "clauses": clauses}
        return node

    def clause(self):
        t = self.cur
        if t.kind in ("KW", "FUNC", "NAME") and t.text.upper() in CLAUSE_KINDS:
            self.i += 1
            self.eat("OP", ":")
            return {"k": t.text.upper(), "m": self.expression()}
        raise ParseError("expected clause kind (SUM/LOOKUP/SELECT/...)", t)

    def primary(self):
        t = self.cur
        if t.kind == "KW":
            if t.text == "IF":
                self.i += 1
                if self.at("OP", "("):
                    # Either classic "IF (cond) AND x THEN ..." or spreadsheet "IF(c, a, b)".
                    # Try classic first; fall back to spreadsheet form on failure.
                    save = self.i
                    try:
                        c = self.expression()
                        self.eat("KW", "THEN")
                        a = self.expression()
                        self.eat("KW", "ELSE")
                        b = self.expression()
                        return {"t": "if", "c": c, "a": a, "b": b}
                    except ParseError:
                        self.i = save
                    self.i += 1
                    c = self.expression(); self.eat("OP", ",")
                    a = self.expression(); self.eat("OP", ",")
                    b = self.expression(); self.eat("OP", ")")
                    return {"t": "if", "c": c, "a": a, "b": b, "form": "spreadsheet"}
                c = self.expression()
                self.eat("KW", "THEN")
                a = self.expression()
                self.eat("KW", "ELSE")
                b = self.expression()
                return {"t": "if", "c": c, "a": a, "b": b}
            if t.text == "TRUE":
                self.i += 1; return {"t": "bool", "v": True}
            if t.text == "FALSE":
                self.i += 1; return {"t": "bool", "v": False}
            if t.text == "BLANK":
                self.i += 1; return {"t": "blank"}
            if t.text in CLAUSE_KINDS and self.peek().kind == "OP" and self.peek().text == "(":
                # SUM( MAX( etc. as ordinary functions
                self.i += 1
                return self.call(t.text)
            raise ParseError("unexpected keyword", t)
        if t.kind == "FUNC":
            self.i += 1
            return self.call(t.text)
        if t.kind == "NUMBER":
            self.i += 1; return {"t": "num", "v": t.text}
        if t.kind == "STRING":
            self.i += 1; return {"t": "str", "v": t.text}
        if t.kind in ("NAME", "QNAME"):
            return self.reference()
        if t.kind == "OP" and t.text == "(":
            self.i += 1
            e = self.expression()
            self.eat("OP", ")")
            return e
        raise ParseError("expected expression", t)

    def call(self, fname):
        self.eat("OP", "(")
        args = []
        if not self.at("OP", ")"):
            args.append(self.argument())
            while self.at("OP", ","):
                self.i += 1
                args.append(self.argument())
        self.eat("OP", ")")
        return {"t": "call", "f": fname, "args": args}

    def argument(self):
        t = self.cur
        if t.kind in ("NAME", "KW", "FUNC") and t.text.upper() in KEYWORD_ARGS and self.peek().kind == "OP" and self.peek().text in (",", ")"):
            self.i += 1
            return {"t": "kwarg", "v": t.text.upper()}
        return self.expression()

    def reference(self):
        path = [self._name()]
        while self.at("OP", ".") and self.peek().kind in ("NAME", "QNAME"):
            self.i += 1
            path.append(self._name())
        return {"t": "ref", "path": path}

    def _name(self):
        t = self.cur
        if t.kind in ("NAME", "QNAME"):
            self.i += 1
            return t.text
        raise ParseError("expected name", t)


def parse(s: str):
    return Parser(s).parse()


def references(node, out=None):
    """Collect every ref path in an AST."""
    if out is None:
        out = []
    if isinstance(node, dict):
        if node.get("t") == "ref":
            out.append(node["path"])
        for v in node.values():
            references(v, out)
    elif isinstance(node, list):
        for v in node:
            references(v, out)
    return out


def references_ctx(node, out=None, fn=None, argi=None):
    """Like references() but each item is (path, enclosing_function, arg_index)
    for refs that are direct arguments of a call, else (path, None, None).
    Lets a resolver treat FINDITEM(List, ...) / ITEM(List) / PARENT(ITEM(List))
    first arguments as list names rather than line items."""
    if out is None:
        out = []
    if isinstance(node, dict):
        t = node.get("t")
        if t == "ref":
            out.append((node["path"], fn, argi))
            return out
        if t == "call":
            for i, a in enumerate(node["args"]):
                references_ctx(a, out, node["f"], i)
            return out
        for v in node.values():
            references_ctx(v, out, None, None)
    elif isinstance(node, list):
        for v in node:
            references_ctx(v, out, None, None)
    return out

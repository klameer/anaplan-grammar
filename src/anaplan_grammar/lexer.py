"""Tokenizer for Anaplan formulas.

Rules learned from the corpus, beyond Anapedia:
- A doubled single quote inside a quoted name is an escaped apostrophe:
  'FOX''s Share' is the name  FOX's Share.
- Bare names may contain spaces, digits, ? % # / | ! and end only at an
  operator character, a bracket, comma, colon, a dot followed by a name
  start, or a *keyword used as a keyword*.
- A keyword (IF THEN ELSE AND OR NOT TRUE FALSE BLANK) or clause kind
  (SUM LOOKUP SELECT ...) is only a keyword when it is a whole word AND
  the following text does not continue a bare name. So "Sum Channels",
  "Lookup Step", "all Phases", "Cumulate Payment" are names; "x AND y",
  "[SUM: x]", "IF a THEN b" are keywords. The test: after the word, skip
  spaces; a keyword is followed by an operator/bracket/paren, another
  keyword, a quote, a digit, or end of input, or (for clause kinds) a
  colon. Anything else means the word begins a bare name.
- A function name followed immediately by "(" is a call.
"""
from __future__ import annotations
from dataclasses import dataclass
import re
from .functions import KEYWORDS, CLAUSE_KINDS, FUNCTIONS


@dataclass
class Tok:
    kind: str      # NAME QNAME NUMBER STRING KW OP FUNC EOF
    text: str
    pos: int

    def __repr__(self):
        return f"{self.kind}({self.text!r}@{self.pos})"


class LexError(Exception):
    def __init__(self, msg, pos):
        super().__init__(f"{msg} at {pos}")
        self.pos = pos


OPS = ["<>", "<=", ">=", "<", ">", "=", "+", "-", "*", "/", "&", "(", ")", "[", "]", ",", ":", "."]
_OP_RE = re.compile("|".join(re.escape(o) for o in OPS))
_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
_STOP = set("+-*/&=<>()[],:\"'")
# Prefix keywords that open an expression: what follows them is an expression start, not a name continuation.
_PREFIX_KW = {"IF", "NOT", "THEN", "ELSE", "AND", "OR"}


def _word_at(s, i):
    m = _WORD_RE.match(s, i)
    return (m.group(0), m.end()) if m else (None, i)


def _keyword_here(s: str, i: int) -> tuple[str | None, int]:
    """Return (KEYWORD, end) if a keyword/clause-kind is used as such at i."""
    w, end = _word_at(s, i)
    if not w:
        return None, i
    up = w.upper()
    is_kw = up in KEYWORDS
    is_clause = up in CLAUSE_KINDS
    if not (is_kw or is_clause):
        return None, i
    # what follows?
    k = end
    while k < len(s) and s[k] == " ":
        k += 1
    nxt = s[k] if k < len(s) else ""
    if is_clause and not is_kw:
        # clause kinds are keywords only in [KIND: ...] or KIND( ... ); otherwise name text
        if nxt in (":", "("):
            return up, end
        return None, i
    if up in _PREFIX_KW:
        # a prefix keyword is followed by an expression: name start, quote, digit, paren, NOT, minus
        if nxt == "" or nxt in "('\"-(" or nxt.isdigit() or nxt.isalpha() or nxt == "_":
            # but "Sum Channels" style: IF/NOT/AND/OR followed by a name is still a keyword
            # (IF x, NOT x, a AND b). THEN/ELSE likewise. So prefix keywords are always keywords
            # when they are whole words. The only exception is when they are the *start* of a
            # bare name, e.g. a line item literally called "Or Something": treat as keyword anyway;
            # corpus shows no such names.
            return up, end
        return up, end
    # TRUE FALSE BLANK: keywords when followed by operator/paren/bracket/comma/keyword/end
    if nxt == "" or nxt in "+-*/&=<>)],:":
        return up, end
    nw, _ = _word_at(s, k)
    if nw and nw.upper() in KEYWORDS:
        return up, end
    return None, i


def tokenize(s: str) -> list[Tok]:
    toks: list[Tok] = []
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c.isspace():
            i += 1
            continue
        if c == "'":
            # quoted name with '' escape
            j = i + 1
            buf = []
            while True:
                if j >= n:
                    raise LexError("unterminated quoted name", i)
                if s[j] == "'":
                    if j + 1 < n and s[j + 1] == "'":
                        buf.append("'")
                        j += 2
                        continue
                    break
                buf.append(s[j])
                j += 1
            toks.append(Tok("QNAME", "".join(buf), i))
            i = j + 1
            continue
        if c == '"':
            j = s.find('"', i + 1)
            if j < 0:
                raise LexError("unterminated string", i)
            toks.append(Tok("STRING", s[i + 1:j], i))
            i = j + 1
            continue
        m = _OP_RE.match(s, i)
        if m:
            toks.append(Tok("OP", m.group(0), i))
            i = m.end()
            continue
        if c.isdigit():
            m = _NUM_RE.match(s, i)
            toks.append(Tok("NUMBER", m.group(0), i))
            i = m.end()
            continue
        kw, end = _keyword_here(s, i)
        if kw:
            toks.append(Tok("KW", kw, i))
            i = end
            continue
        w, end = _word_at(s, i)
        if w and w.upper() in FUNCTIONS and end < n and s[end] == "(":
            toks.append(Tok("FUNC", w.upper(), i))
            i = end
            continue
        # bare name
        start = i
        j = i
        while j < n:
            ch = s[j]
            if ch in _STOP:
                break
            if ch == ".":
                k = j + 1
                while k < n and s[k] == " ":
                    k += 1
                if k < n and (s[k].isalpha() or s[k] in "_'%#"):
                    break
                j += 1
                continue
            if ch == " ":
                k = j + 1
                while k < n and s[k] == " ":
                    k += 1
                if k >= n:
                    break
                kw2, _ = _keyword_here(s, k)
                if kw2:
                    break
                j += 1
                continue
            j += 1
        text = s[start:j].rstrip()
        if not text:
            raise LexError(f"unexpected character {c!r}", i)
        toks.append(Tok("NAME", text, start))
        i = j
    toks.append(Tok("EOF", "", n))
    return toks

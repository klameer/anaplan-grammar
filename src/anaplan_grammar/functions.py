"""Anaplan function catalogue. Source: Anapedia 'All functions' page,
fetched 2026-09-21 (help.anaplan.com/all-functions-160769b0-...).
Names only; arity and argument types are added per function as the
parser needs them. Duplicated names (MAX, MIN, TEXTLIST) exist as both
aggregation-clause kinds and numeric/text functions; the parser decides
by position (inside [..:] versus followed by '(')."""

FUNCTIONS = {
    # numeric
    "ABS", "DIVIDE", "EXP", "FIRSTNONZERO", "LN", "LOG", "MAX", "MIN", "MOD",
    "MROUND", "POWER", "ROUND", "SIGN", "SQRT",
    # trig / maths
    "ACOS", "ACOSH", "ASIN", "ASINH", "ATAN", "ATANH", "COS", "COSH", "E", "PI",
    "SIN", "SINH", "TAN", "TANH", "TODEGREES", "TORADIANS",
    # time and date
    "ADDMONTHS", "ADDYEARS", "CUMULATE", "CURRENTPERIODEND", "CURRENTPERIODSTART",
    "DATE", "DAY", "DAYS", "DAYSINMONTH", "DAYSINYEAR", "DECUMULATE", "END",
    "HALFYEARTODATE", "HALFYEARVALUE", "INPERIOD", "LAG", "LEAD", "MONTH",
    "MONTHTODATE", "MONTHVALUE", "MOVINGSUM", "NEXT", "OFFSET", "PERIOD", "POST",
    "PREVIOUS", "PROFILE", "QUARTERTODATE", "QUARTERVALUE", "SPREAD", "START",
    "TIMESUM", "WEEKDAY", "WEEKTODATE", "WEEKVALUE", "YEAR", "YEARTODATE",
    "YEARVALUE",
    # aggregation (also clause kinds)
    "ALL", "ANY", "AVERAGE", "FIRSTNONBLANK", "LASTNONBLANK", "STDEVP", "STDEVS",
    "SUM", "TEXTLIST", "VARP", "VARS",
    # logical
    "COMPARE", "IF", "ISACTUALVERSION", "ISANCESTOR", "ISBLANK", "ISCURRENTVERSION",
    "ISFIRSTOCCURRENCE", "ISNOTBLANK",
    # text
    "FIND", "LEFT", "LENGTH", "LOWER", "MAILTO", "MAKELINK", "MID", "NAME", "RIGHT",
    "SUBSTITUTE", "TEXT", "TRIM", "UPPER",
    # mapping
    "LOOKUP", "SELECT",
    # miscellaneous
    "CODE", "COLLECT", "CURRENTVERSION", "FINDITEM", "HIERARCHYLEVEL", "ITEM",
    "ITEMLEVEL", "NEXTVERSION", "PARENT", "PREVIOUSVERSION", "RANK", "RANKCUMULATE",
    "VALUE",
    # financial
    "COUPDAYBS", "COUPDAYS", "COUPDAYSNC", "COUPNCD", "COUPNUM", "COUPPCD",
    "CUMIPMT", "CUMPRINC", "DURATION", "FV", "IPMT", "IRR", "MDURATION", "NPER",
    "NPV", "PMT", "PPMT", "PRICE", "PV", "RATE", "YEARFRAC", "YIELD",
    # call centre planning
    "AGENTS", "AGENTSB", "ANSWERTIME", "ARRIVALRATE", "AVGDURATION", "AVGWAIT",
    "ERLANGB", "ERLANGC", "SLA",
}

CLAUSE_KINDS = {
    "SUM", "LOOKUP", "SELECT", "AVERAGE", "MIN", "MAX", "ANY", "ALL",
    "FIRSTNONBLANK", "LASTNONBLANK", "TEXTLIST", "STDEVS", "STDEVP", "VARS", "VARP",
}

# Bare keyword arguments accepted inside function calls (RANK direction,
# CUMULATE/MOVINGSUM aggregation, SPREAD/PROFILE modes, TIMESUM aggregation).
KEYWORD_ARGS = {
    "ASCENDING", "DESCENDING", "MINIMUM", "MAXIMUM", "SEQUENTIAL", "STRICT",
    "START", "END", "MID", "LINEAR", "NONE", "AVERAGE", "SUM", "MIN", "MAX",
    "FIRSTNONBLANK", "LASTNONBLANK", "TEXTLIST", "ANY", "ALL", "TRUE", "FALSE",
    "NEAREST", "UNIQUE", "NONSTRICT", "SEMISTRICT", "TOWARDS_ZERO", "TOWARDSZERO", "AWAY_FROM_ZERO", "AWAYFROMZERO", "UP", "DOWN", "EXACT", "NORMAL", "SIMPLE",
}

KEYWORDS = {"IF", "THEN", "ELSE", "AND", "OR", "NOT", "TRUE", "FALSE", "BLANK"}

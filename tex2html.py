#!/usr/bin/env python3
"""Convert an acmart LaTeX paper and its BibTeX database into a single HTML file.

Usage:
    python tex2html.py paper.tex [-b references.bib] [-o paper.html]

The generated document is ASCII only, links to ../papers.css, resolves figure
paths to ./figures/, and renders the bibliography in ACM Reference Format,
numbered by alphabetical author order.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from html.entities import codepoint2name
from typing import Iterable, Sequence


ENTITY_OVERRIDES = {
    0x00A0: "nbsp",
    0x2018: "lsquo",
    0x2019: "rsquo",
    0x201C: "ldquo",
    0x201D: "rdquo",
    0x2013: "ndash",
    0x2014: "mdash",
    0x2026: "hellip",
}


def escape(text: str) -> str:
    """Escape markup characters and replace every non-ASCII character."""
    out = []
    for ch in text:
        code = ord(ch)
        if ch == "&":
            out.append("&amp;")
        elif ch == "<":
            out.append("&lt;")
        elif ch == ">":
            out.append("&gt;")
        elif code < 128:
            out.append(ch)
        else:
            name = ENTITY_OVERRIDES.get(code) or codepoint2name.get(code)
            out.append("&%s;" % name if name else "&#%d;" % code)
    return "".join(out)


def escape_attr(text: str) -> str:
    return escape(text).replace('"', "&quot;")


def collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def slugify(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return text or "section"


@dataclass
class Text:
    value: str


@dataclass
class Command:
    name: str
    star: bool = False
    opts: list = field(default_factory=list)
    args: list = field(default_factory=list)


@dataclass
class Group:
    nodes: list = field(default_factory=list)


@dataclass
class Environment:
    name: str
    opts: list = field(default_factory=list)
    args: list = field(default_factory=list)
    body: list = field(default_factory=list)


@dataclass
class Verbatim:
    name: str
    content: str
    language: str = ""


@dataclass
class Math:
    content: str
    display: bool = False


@dataclass
class ParagraphBreak:
    pass


VERBATIM_ENVIRONMENTS = {"verbatim", "Verbatim", "lstlisting", "minted", "alltt"}

DROPPED_ENVIRONMENTS = {"CCSXML", "comment"}

METADATA_COMMANDS = {
    "title", "subtitle", "author", "affiliation", "email", "orcid", "authornote",
    "authorsaddresses", "thanks", "acmConference", "acmBooktitle", "acmDOI",
    "acmISBN", "acmYear", "acmJournal", "acmVolume", "acmNumber", "acmArticle",
    "acmMonth", "acmPrice", "copyrightyear", "setcopyright", "setcctype",
    "keywords", "ccsdesc", "documentclass", "usepackage", "pagenumbering",
    "lstset", "AtBeginDocument", "settopmatter", "received", "acmSubmissionID",
    "editor", "titlenote", "subtitlenote",
}

DISPLAY_MATH_ENVIRONMENTS = {
    "equation",
    "equation*",
    "align",
    "align*",
    "gather",
    "gather*",
    "eqnarray",
    "eqnarray*",
    "multline",
    "multline*",
    "displaymath",
}

ENVIRONMENT_ARGUMENTS = {
    "tabular": (1, 1),
    "tabular*": (1, 2),
    "tabularx": (1, 2),
    "array": (1, 1),
    "figure": (1, 0),
    "figure*": (1, 0),
    "table": (1, 0),
    "table*": (1, 0),
    "subfigure": (1, 1),
    "minipage": (1, 1),
    "wrapfigure": (1, 2),
    "lstlisting": (1, 0),
    "itemize": (1, 0),
    "enumerate": (1, 0),
    "description": (1, 0),
    "theorem": (1, 0),
    "lemma": (1, 0),
    "definition": (1, 0),
}

COMMAND_ARGUMENTS = {
    "title": (1, 1),
    "subtitle": (0, 1),
    "author": (1, 1),
    "affiliation": (1, 1),
    "institution": (1, 1),
    "department": (1, 1),
    "city": (1, 1),
    "state": (1, 1),
    "country": (1, 1),
    "postcode": (1, 1),
    "streetaddress": (1, 1),
    "email": (1, 1),
    "orcid": (0, 1),
    "authornote": (0, 1),
    "authorsaddresses": (0, 1),
    "thanks": (0, 1),
    "acmConference": (1, 3),
    "acmBooktitle": (0, 1),
    "acmDOI": (0, 1),
    "acmISBN": (0, 1),
    "acmYear": (0, 1),
    "acmJournal": (0, 1),
    "acmVolume": (0, 1),
    "acmNumber": (0, 1),
    "acmArticle": (0, 1),
    "acmMonth": (0, 1),
    "acmPrice": (0, 1),
    "copyrightyear": (0, 1),
    "setcopyright": (0, 1),
    "setcctype": (1, 1),
    "keywords": (0, 1),
    "ccsdesc": (1, 1),
    "renewcommand": (0, 2),
    "providecommand": (1, 2),
    "documentclass": (1, 1),
    "usepackage": (1, 1),
    "bibliographystyle": (0, 1),
    "pagenumbering": (0, 1),
    "lstset": (0, 1),
    "AtBeginDocument": (0, 1),
    "settopmatter": (0, 1),
    "received": (1, 1),
    "bibliography": (0, 1),
    "section": (1, 1),
    "subsection": (1, 1),
    "subsubsection": (1, 1),
    "paragraph": (1, 1),
    "subparagraph": (1, 1),
    "caption": (1, 1),
    "label": (0, 1),
    "ref": (0, 1),
    "autoref": (0, 1),
    "eqref": (0, 1),
    "pageref": (0, 1),
    "cite": (2, 1),
    "citep": (2, 1),
    "citet": (2, 1),
    "citeauthor": (0, 1),
    "citeyear": (0, 1),
    "nocite": (0, 1),
    "footnote": (1, 1),
    "footnotetext": (1, 1),
    "href": (0, 2),
    "url": (0, 1),
    "textit": (0, 1),
    "textbf": (0, 1),
    "textsc": (0, 1),
    "texttt": (0, 1),
    "textrm": (0, 1),
    "textsf": (0, 1),
    "textsuperscript": (0, 1),
    "textsubscript": (0, 1),
    "underline": (0, 1),
    "uline": (0, 1),
    "emph": (0, 1),
    "textnormal": (0, 1),
    "mbox": (0, 1),
    "text": (0, 1),
    "includegraphics": (1, 1),
    "Description": (1, 1),
    "multicolumn": (0, 3),
    "multirow": (1, 3),
    "thead": (1, 1),
    "makecell": (1, 1),
    "rowcolor": (1, 1),
    "cellcolor": (1, 1),
    "cmidrule": (2, 1),
    "rule": (1, 2),
    "fcolorbox": (1, 3),
    "arrayrulecolor": (0, 1),
    "noalign": (0, 1),
    "definecolor": (1, 3),
    "appendix": (0, 0),
    "item": (1, 0),
    "hspace": (1, 1),
    "vspace": (1, 1),
    "linebreak": (1, 0),
    "phantom": (0, 1),
    "hphantom": (0, 1),
    "vphantom": (0, 1),
    "raisebox": (2, 2),
    "setlength": (0, 2),
    "resizebox": (0, 3),
    "scalebox": (1, 2),
    "colorbox": (0, 2),
    "fbox": (0, 1),
    "framebox": (2, 1),
    "textcolor": (0, 2),
    "footnotemark": (1, 0),
    "shortauthors": (0, 0),
}

TEX_REGISTERS = {
    "looseness",
    "tolerance",
    "pretolerance",
    "hbadness",
    "vbadness",
    "clubpenalty",
    "widowpenalty",
    "displaywidowpenalty",
    "interlinepenalty",
    "brokenpenalty",
    "emergencystretch",
    "parindent",
    "parskip",
    "baselineskip",
    "lineskip",
    "abovedisplayskip",
    "belowdisplayskip",
    "topsep",
    "partopsep",
    "itemsep",
    "parsep",
    "leftmargini",
    "tabcolsep",
    "arrayrulewidth",
    "doublerulesep",
    "extrarowheight",
    "footnotesep",
    "columnsep",
    "textfloatsep",
    "floatsep",
    "intextsep",
    "abovecaptionskip",
    "belowcaptionskip",
}

DIMENSION = r"[-+]?\d*\.?\d+\s*(?:pt|pc|in|bp|cm|mm|dd|cc|sp|ex|em|mu)?"

ACCENT_COMMANDS = {
    "`": "\u0300",
    "'": "\u0301",
    "^": "\u0302",
    '"': "\u0308",
    "~": "\u0303",
    "=": "\u0304",
    ".": "\u0307",
    "u": "\u0306",
    "v": "\u030C",
    "c": "\u0327",
    "H": "\u030B",
    "r": "\u030A",
    "k": "\u0328",
}

SYMBOL_COMMANDS = {
    "textless": "<",
    "textgreater": ">",
    "textbar": "|",
    "textbackslash": "\\",
    "textasciitilde": "~",
    "textasciicircum": "^",
    "textunderscore": "_",
    "textbraceleft": "{",
    "textbraceright": "}",
    "textdollar": "$",
    "textasteriskcentered": "*",
    "textperiodcentered": "\u00b7",
    "textsection": "\u00a7",
    "textparagraph": "\u00b6",
    "textdagger": "\u2020",
    "textdaggerdbl": "\u2021",
    "textpm": "\u00b1",
    "textmu": "\u00b5",
    "textonehalf": "\u00bd",
    "textonequarter": "\u00bc",
    "textthreequarters": "\u00be",
    "textcent": "\u00a2",
    "textyen": "\u00a5",
    "textcelsius": "\u2103",
    "textnumero": "\u2116",
    "textquoteright": "\u2019",
    "textquoteleft": "\u2018",
    "textquotedblright": "\u201d",
    "textquotedblleft": "\u201c",
    "textendash": "\u2013",
    "textemdash": "\u2014",
    "textellipsis": "\u2026",
    "ldots": "\u2026",
    "dots": "\u2026",
    "textsterling": "\u00a3",
    "pounds": "\u00a3",
    "texteuro": "\u20ac",
    "textdegree": "\u00b0",
    "textbullet": "\u2022",
    "textregistered": "\u00ae",
    "texttrademark": "\u2122",
    "copyright": "\u00a9",
    "textcopyright": "\u00a9",
    "ss": "\u00df",
    "ae": "\u00e6",
    "AE": "\u00c6",
    "oe": "\u0153",
    "OE": "\u0152",
    "o": "\u00f8",
    "O": "\u00d8",
    "aa": "\u00e5",
    "AA": "\u00c5",
    "l": "\u0142",
    "L": "\u0141",
    "i": "i",
    "j": "j",
    "&": "&",
    "%": "%",
    "$": "$",
    "#": "#",
    "_": "_",
    "{": "{",
    "}": "}",
    " ": " ",
    ",": " ",
    ";": " ",
    ":": " ",
    "!": "",
    "/": "",
    "@": "",
    "-": "",
}

IGNORED_COMMANDS = {
    "maketitle",
    "centering",
    "raggedright",
    "raggedleft",
    "balance",
    "clearpage",
    "newpage",
    "leavevmode",
    "begingroup",
    "endgroup",
    "bgroup",
    "egroup",
    "global",
    "protect",
    "relax",
    "ignorespaces",
    "normalfont",
    "arrayrulecolor",
    "noalign",
    "definecolor",
    "onecolumn",
    "twocolumn",
    "noindent",
    "indent",
    "small",
    "footnotesize",
    "scriptsize",
    "tiny",
    "large",
    "Large",
    "LARGE",
    "huge",
    "Huge",
    "normalsize",
    "bfseries",
    "itshape",
    "rmfamily",
    "sffamily",
    "ttfamily",
    "hfill",
    "hfil",
    "vfill",
    "dotfill",
    "hrulefill",
    "smallskip",
    "medskip",
    "bigskip",
    "strut",
    "allowbreak",
    "unskip",
    "hspace",
    "vspace",
    "setlength",
    "addtolength",
    "phantom",
    "hphantom",
    "vphantom",
    "cmidrule",
    "toprule",
    "midrule",
    "bottomrule",
    "hline",
    "linewidth",
    "columnwidth",
    "textwidth",
    "arraybackslash",
    "printbibliography",
    "newcommand",
    "renewcommand",
    "providecommand",
    "def",
    "cellcolor",
    "rowcolor",
    "columncolor",
    "arraystretch",
    "listoffigures",
    "listoftables",
    "tableofcontents",
    "shortauthors",
    "startsection",
    "par",
}


class LatexParser:
    """Turn LaTeX source into a flat tree of text, command, and environment nodes."""

    def __init__(self, source: str):
        self.src = self._strip_comments(source)
        self.pos = 0
        self.macros: dict[str, tuple[int, str]] = {}
        self._scan_macros()

    @staticmethod
    def _strip_comments(source: str) -> str:
        lines = []
        for line in source.split("\n"):
            out = []
            escaped = False
            for index, ch in enumerate(line):
                if escaped:
                    out.append(ch)
                    escaped = False
                    continue
                if ch == "\\":
                    out.append(ch)
                    escaped = True
                    continue
                if ch == "%":
                    break
                out.append(ch)
            lines.append("".join(out))
        return "\n".join(lines)

    def _scan_macros(self) -> None:
        pattern = re.compile(r"\\(?:new|renew|provide)command\*?\s*\{?\\([A-Za-z@]+)\}?\s*(\[(\d+)\])?")
        for match in pattern.finditer(self.src):
            name, _, count = match.groups()
            if name not in COMMAND_ARGUMENTS:
                self.macros[name] = (int(count or 0), "")

    def parse(self) -> list:
        return self._parse_nodes(None)

    def _parse_nodes(self, stop_env: str | None) -> list:
        nodes: list = []
        buffer: list[str] = []

        def flush() -> None:
            if buffer:
                nodes.append(Text("".join(buffer)))
                buffer.clear()

        while self.pos < len(self.src):
            ch = self.src[self.pos]
            if ch == "\\":
                match = re.match(r"\\([A-Za-z@]+\*?|.)", self.src[self.pos:], re.S)
                if not match:
                    buffer.append(ch)
                    self.pos += 1
                    continue
                name = match.group(1)
                if name == "begin":
                    flush()
                    self.pos += match.end()
                    nodes.append(self._parse_environment())
                    continue
                if name == "end":
                    self.pos += match.end()
                    closing = self._read_group_text()
                    flush()
                    if closing != stop_env:
                        nodes.append(Command("end-mismatch", args=[[Text(closing)]]))
                    return nodes
                if name in ("[", "]"):
                    flush()
                    if name == "[":
                        self.pos += match.end()
                        nodes.append(Math(self._read_until(r"\]"), display=True))
                    else:
                        self.pos += match.end()
                    continue
                if name in ("(", ")"):
                    flush()
                    if name == "(":
                        self.pos += match.end()
                        nodes.append(Math(self._read_until(r"\)")))
                    else:
                        self.pos += match.end()
                    continue
                if name in ("verb", "lstinline"):
                    self.pos += match.end()
                    flush()
                    nodes.append(self._parse_inline_verbatim(name))
                    continue
                self.pos += match.end()
                flush()
                nodes.append(self._parse_command(name))
                continue
            if ch == "{":
                flush()
                self.pos += 1
                nodes.append(Group(self._parse_group_nodes()))
                continue
            if ch == "}":
                self.pos += 1
                flush()
                return nodes
            if ch == "$":
                flush()
                if self.src.startswith("$$", self.pos):
                    self.pos += 2
                    nodes.append(Math(self._read_until("$$"), display=True))
                else:
                    self.pos += 1
                    nodes.append(Math(self._read_until("$")))
                continue
            if ch == "\n" and re.match(r"\n\s*\n", self.src[self.pos:]):
                flush()
                skipped = re.match(r"\s*\n\s*", self.src[self.pos:])
                self.pos += skipped.end()
                nodes.append(ParagraphBreak())
                continue
            buffer.append(ch)
            self.pos += 1

        flush()
        return nodes

    def _parse_group_nodes(self) -> list:
        return self._parse_nodes(stop_env="\0group")

    def _parse_environment(self) -> Environment | Verbatim | Math:
        name = self._read_group_text()
        if name in VERBATIM_ENVIRONMENTS or name in DROPPED_ENVIRONMENTS:
            options = self._read_optional_raw()
            end = "\\end{%s}" % name
            index = self.src.find(end, self.pos)
            if index < 0:
                index = len(self.src)
            content = self.src[self.pos:index]
            self.pos = min(index + len(end), len(self.src))
            language = ""
            found = re.search(r"language\s*=\s*([A-Za-z+#]+)", options or "")
            if found:
                language = found.group(1).lower()
            return Verbatim(name, content.strip("\n"), language)
        if name in DISPLAY_MATH_ENVIRONMENTS:
            end = "\\end{%s}" % name
            index = self.src.find(end, self.pos)
            if index < 0:
                index = len(self.src)
            content = self.src[self.pos:index]
            self.pos = min(index + len(end), len(self.src))
            return Math(content.strip(), display=True)

        opt_count, arg_count = ENVIRONMENT_ARGUMENTS.get(name, (1, 0))
        opts = self._read_optionals(opt_count)
        args = self._read_arguments(arg_count)
        body = self._parse_nodes(stop_env=name)
        return Environment(name, opts, args, body)

    def _parse_inline_verbatim(self, name: str) -> Verbatim:
        while self.pos < len(self.src) and self.src[self.pos] in " \t":
            self.pos += 1
        if self.pos >= len(self.src):
            return Verbatim(name, "")
        opening = self.src[self.pos]
        closing = {"{": "}", "[": "]", "(": ")"}.get(opening, opening)
        self.pos += 1
        index = self.src.find(closing, self.pos)
        if index < 0:
            index = len(self.src)
        content = self.src[self.pos:index]
        self.pos = min(index + 1, len(self.src))
        return Verbatim(name, content)

    def _parse_command(self, raw_name: str) -> Command:
        star = raw_name.endswith("*")
        name = raw_name[:-1] if star else raw_name
        if name in ("newcommand", "renewcommand", "providecommand", "def"):
            return self._parse_macro_definition(name)
        if name in TEX_REGISTERS:
            self._skip_register_value()
            return Command(name)
        if name in COMMAND_ARGUMENTS:
            opt_count, arg_count = COMMAND_ARGUMENTS[name]
        elif name in self.macros:
            opt_count, arg_count = 0, self.macros[name][0]
        elif name in ACCENT_COMMANDS or name in SYMBOL_COMMANDS or name in IGNORED_COMMANDS:
            opt_count, arg_count = 0, 0
        else:
            opt_count, arg_count = 0, 0
        if name in ACCENT_COMMANDS and self._peek_is_group_or_letter():
            return Command(name, star, [], [self._read_accent_argument()])
        opts = self._read_optionals(opt_count)
        args = self._read_arguments(arg_count)
        if name.isalpha() and not args and not opts:
            while self.pos < len(self.src) and self.src[self.pos] in " \t":
                self.pos += 1
        return Command(name, star, opts, args)

    def _parse_macro_definition(self, name: str) -> Command:
        self._skip_whitespace()
        if self.pos < len(self.src) and self.src[self.pos] == "{":
            target = self._read_group_text().strip()
        else:
            match = re.match(r"\\([A-Za-z@]+)", self.src[self.pos:])
            target = match.group(0) if match else ""
            self.pos += match.end() if match else 0
        target = target.lstrip("\\").strip()
        count_raw = self._read_optional_raw()
        default = self._read_optional_raw()
        body = self._read_raw_group()
        count = int(count_raw) if count_raw and count_raw.strip().isdigit() else 0
        if target and target not in COMMAND_ARGUMENTS and target not in IGNORED_COMMANDS:
            self.macros[target] = (count, body)
        return Command(name)

    def _skip_register_value(self) -> None:
        """Consume the value of a TeX register assignment such as \\looseness-1 or \\parskip=6pt plus 2pt."""
        pattern = r"[ \t]*=?[ \t]*" + DIMENSION + r"(?:\s*(?:plus|minus)\s*" + DIMENSION + r")*[ \t]*"
        match = re.match(pattern, self.src[self.pos:])
        if match and match.group(0).strip(" \t="):
            self.pos += match.end()

    def _read_raw_group(self) -> str:
        self._skip_whitespace()
        if self.pos >= len(self.src) or self.src[self.pos] != "{":
            return ""
        return self._read_group_text()

    def _peek_is_group_or_letter(self) -> bool:
        index = self.pos
        while index < len(self.src) and self.src[index] in " \t":
            index += 1
        return index < len(self.src) and (self.src[index] == "{" or self.src[index].isalpha())

    def _read_accent_argument(self) -> list:
        while self.pos < len(self.src) and self.src[self.pos] in " \t":
            self.pos += 1
        if self.pos < len(self.src) and self.src[self.pos] == "{":
            self.pos += 1
            return self._parse_group_nodes()
        ch = self.src[self.pos]
        self.pos += 1
        return [Text(ch)]

    def _skip_whitespace(self) -> None:
        while self.pos < len(self.src) and self.src[self.pos] in " \t\n":
            self.pos += 1

    def _read_optionals(self, count: int) -> list:
        opts = []
        for _ in range(count):
            saved = self.pos
            self._skip_whitespace()
            if self.pos < len(self.src) and self.src[self.pos] == "[":
                self.pos += 1
                opts.append(self._parse_bracket_nodes())
            else:
                self.pos = saved
                break
        return opts

    def _read_optional_raw(self) -> str | None:
        saved = self.pos
        self._skip_whitespace()
        if self.pos < len(self.src) and self.src[self.pos] == "[":
            depth = 0
            start = self.pos + 1
            while self.pos < len(self.src):
                ch = self.src[self.pos]
                if ch == "[":
                    depth += 1
                elif ch == "]":
                    depth -= 1
                    if depth == 0:
                        raw = self.src[start:self.pos]
                        self.pos += 1
                        return raw
                self.pos += 1
        self.pos = saved
        return None

    def _parse_bracket_nodes(self) -> list:
        depth = 1
        start = self.pos
        while self.pos < len(self.src) and depth:
            ch = self.src[self.pos]
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    break
            self.pos += 1
        raw = self.src[start:self.pos]
        self.pos += 1
        sub = LatexParser(raw)
        sub.macros = self.macros
        return sub.parse()

    def _read_arguments(self, count: int) -> list:
        args = []
        for _ in range(count):
            saved = self.pos
            self._skip_whitespace()
            if self.pos < len(self.src) and self.src[self.pos] == "{":
                self.pos += 1
                args.append(self._parse_group_nodes())
            elif self.pos < len(self.src) and self.src[self.pos] == "\\":
                match = re.match(r"\\([A-Za-z@]+\*?|.)", self.src[self.pos:], re.S)
                self.pos += match.end()
                args.append([Command(match.group(1))])
            elif self.pos < len(self.src) and self.src[self.pos] not in "}]&$[":
                args.append([Text(self.src[self.pos])])
                self.pos += 1
            else:
                self.pos = saved
                break
        return args

    def _read_group_text(self) -> str:
        self._skip_whitespace()
        if self.pos >= len(self.src) or self.src[self.pos] != "{":
            return ""
        depth = 0
        start = self.pos + 1
        while self.pos < len(self.src):
            ch = self.src[self.pos]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    text = self.src[start:self.pos]
                    self.pos += 1
                    return text
            self.pos += 1
        return ""

    def _read_until(self, terminator: str) -> str:
        index = self.src.find(terminator, self.pos)
        if index < 0:
            index = len(self.src)
        content = self.src[self.pos:index]
        self.pos = min(index + len(terminator), len(self.src))
        return content


def find_environment(nodes: Sequence, *names: str) -> Environment | None:
    """Find the first environment with one of the given names, including inside command arguments."""
    for node in nodes:
        if isinstance(node, Environment):
            if node.name in names:
                return node
            found = find_environment(node.body, *names)
            if found:
                return found
        elif isinstance(node, Group):
            found = find_environment(node.nodes, *names)
            if found:
                return found
        elif isinstance(node, Command):
            for group in list(node.opts) + list(node.args):
                found = find_environment(group, *names)
                if found:
                    return found
    return None


def iter_commands(nodes: Iterable, name: str) -> Iterable[Command]:
    for node in nodes:
        if isinstance(node, Command) and node.name == name:
            yield node
        elif isinstance(node, Group):
            yield from iter_commands(node.nodes, name)
        elif isinstance(node, Environment):
            yield from iter_commands(node.body, name)


MONTHS = {
    "jan": "Jan.", "feb": "Feb.", "mar": "March", "apr": "April",
    "may": "May", "jun": "June", "jul": "July", "aug": "Aug.",
    "sep": "Sept.", "oct": "Oct.", "nov": "Nov.", "dec": "Dec.",
    "1": "Jan.", "2": "Feb.", "3": "March", "4": "April", "5": "May",
    "6": "June", "7": "July", "8": "Aug.", "9": "Sept.", "10": "Oct.",
    "11": "Nov.", "12": "Dec.",
}

NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "phd", "md"}

NAME_PARTICLES = {"van", "von", "der", "den", "de", "di", "del", "della", "la", "le", "du", "dos", "da"}


@dataclass
class Name:
    first: str
    last: str
    suffix: str = ""

    def display(self) -> str:
        parts = [part for part in (self.first, self.last) if part]
        text = " ".join(parts)
        if self.suffix:
            text += ", " + self.suffix
        return text

    def sort_key(self) -> tuple:
        return (plain(self.last), plain(self.first))


@dataclass
class BibEntry:
    key: str
    kind: str
    fields: dict

    def get(self, *names: str) -> str:
        for name in names:
            value = self.fields.get(name)
            if value:
                return value
        return ""


class BibParser:
    """Read a BibTeX file into BibEntry objects, ignoring @string and @comment."""

    def __init__(self, source: str):
        self.src = source
        self.pos = 0

    def parse(self) -> dict:
        entries: dict[str, BibEntry] = {}
        while True:
            index = self.src.find("@", self.pos)
            if index < 0:
                break
            self.pos = index + 1
            match = re.match(r"\s*([A-Za-z]+)\s*[{(]", self.src[self.pos:])
            if not match:
                continue
            kind = match.group(1).lower()
            self.pos += match.end()
            body = self._read_balanced()
            if kind in ("string", "comment", "preamble"):
                continue
            entry = self._parse_entry(kind, body)
            if entry:
                entries[entry.key] = entry
        return entries

    def _read_balanced(self) -> str:
        depth = 1
        start = self.pos
        while self.pos < len(self.src):
            ch = self.src[self.pos]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    text = self.src[start:self.pos]
                    self.pos += 1
                    return text
            self.pos += 1
        return self.src[start:]

    def _parse_entry(self, kind: str, body: str) -> BibEntry | None:
        parts = self._split_fields(body)
        if not parts:
            return None
        key = parts[0].strip().rstrip(",").strip()
        fields: dict[str, str] = {}
        for part in parts[1:]:
            if "=" not in part:
                continue
            name, _, value = part.partition("=")
            name = name.strip().lower()
            if name and name not in fields:
                fields[name] = self._clean_value(value.strip())
        return BibEntry(key, kind, fields)

    @staticmethod
    def _split_fields(body: str) -> list[str]:
        parts = []
        depth = 0
        quoted = False
        current = []
        for ch in body:
            if ch == "{" and not quoted:
                depth += 1
            elif ch == "}" and not quoted:
                depth -= 1
            elif ch == '"' and depth == 0:
                quoted = not quoted
            if ch == "," and depth == 0 and not quoted:
                parts.append("".join(current))
                current = []
                continue
            current.append(ch)
        parts.append("".join(current))
        return [part for part in parts if part.strip()]

    @staticmethod
    def _clean_value(value: str) -> str:
        value = value.strip()
        if value.startswith("{") and value.endswith("}"):
            value = value[1:-1]
        elif value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        return collapse(value)


def parse_names(field: str) -> list[Name]:
    """Split a BibTeX author or editor field into individual names."""
    if not field:
        return []
    people = []
    depth = 0
    current = []
    tokens = field.split(" ")
    for token in tokens:
        depth += token.count("{") - token.count("}")
        if token == "and" and depth == 0 and current:
            people.append(" ".join(current))
            current = []
            continue
        current.append(token)
    if current:
        people.append(" ".join(current))

    names = []
    for raw in people:
        raw = collapse(raw)
        if not raw:
            continue
        if raw.startswith("{") and raw.endswith("}") and "{" not in raw[1:-1]:
            names.append(Name("", collapse(raw[1:-1])))
            continue
        chunks = split_outside_braces(raw, ",")
        if len(chunks) > 1:
            last = chunks[0]
            suffix = ""
            first = chunks[-1]
            if len(chunks) > 2:
                if chunks[-1].lower().rstrip(".") in NAME_SUFFIXES:
                    suffix, first = chunks[-1], chunks[1]
                else:
                    suffix = chunks[1]
            names.append(Name(collapse(first), collapse(last), collapse(suffix)))
            continue
        words = raw.split(" ")
        if len(words) == 1:
            names.append(Name("", collapse(words[0])))
            continue
        split_at = len(words) - 1
        while split_at > 1 and words[split_at - 1].lower() in NAME_PARTICLES:
            split_at -= 1
        first = " ".join(words[:split_at])
        last = " ".join(words[split_at:])
        names.append(Name(collapse(first), collapse(last)))
    return names


def plain(source: str) -> str:
    """Reduce a name or title to a lowercase ASCII form suitable for sorting."""
    import html as html_module
    import unicodedata

    text = html_module.unescape(re.sub(r"<[^>]+>", "", inline_latex(source)))
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if ch.isalnum() or ch.isspace()).lower().strip()


def split_outside_braces(text: str, separator: str) -> list[str]:
    """Split on a separator, ignoring occurrences inside brace groups."""
    parts = []
    depth = 0
    current = []
    for ch in text:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        if ch == separator and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(ch)
    parts.append("".join(current).strip())
    return [part for part in parts if part]


def strip_braces(text: str) -> str:
    return collapse(text.replace("{", "").replace("}", ""))


COMMAND_ARGUMENTS["\\"] = (1, 0)

GREEK = {
    "alpha": "&alpha;", "beta": "&beta;", "gamma": "&gamma;", "delta": "&delta;",
    "epsilon": "&epsilon;", "zeta": "&zeta;", "eta": "&eta;", "theta": "&theta;",
    "iota": "&iota;", "kappa": "&kappa;", "lambda": "&lambda;", "mu": "&mu;",
    "nu": "&nu;", "xi": "&xi;", "pi": "&pi;", "rho": "&rho;", "sigma": "&sigma;",
    "tau": "&tau;", "upsilon": "&upsilon;", "phi": "&phi;", "chi": "&chi;",
    "psi": "&psi;", "omega": "&omega;", "Gamma": "&Gamma;", "Delta": "&Delta;",
    "Theta": "&Theta;", "Lambda": "&Lambda;", "Xi": "&Xi;", "Pi": "&Pi;",
    "Sigma": "&Sigma;", "Phi": "&Phi;", "Psi": "&Psi;", "Omega": "&Omega;",
}

MATH_SYMBOLS = {
    "times": "&times;", "cdot": "&middot;", "div": "&divide;", "pm": "&plusmn;",
    "mp": "&#8723;", "leq": "&le;", "le": "&le;", "geq": "&ge;", "ge": "&ge;",
    "neq": "&ne;", "ne": "&ne;", "approx": "&asymp;", "equiv": "&equiv;",
    "sim": "&sim;", "propto": "&prop;", "infty": "&infin;", "sum": "&sum;",
    "prod": "&prod;", "int": "&int;", "partial": "&part;", "nabla": "&nabla;",
    "forall": "&forall;", "exists": "&exist;", "in": "&isin;", "notin": "&notin;",
    "subset": "&sub;", "subseteq": "&sube;", "cup": "&cup;", "cap": "&cap;",
    "rightarrow": "&rarr;", "to": "&rarr;", "leftarrow": "&larr;",
    "Rightarrow": "&rArr;", "Leftarrow": "&lArr;", "leftrightarrow": "&harr;",
    "ldots": "&hellip;", "dots": "&hellip;", "cdots": "&hellip;",
    "quad": " ", "qquad": " ", ",": " ", ";": " ", "!": "", " ": " ",
    "%": "%", "&": "&amp;", "#": "#", "_": "_", "{": "{", "}": "}", "$": "$",
    "star": "&#8902;", "circ": "&#8728;", "bullet": "&bull;", "prime": "&prime;",
    "square": "&#9633;", "Box": "&#9633;", "blacksquare": "&#9632;",
    "checkmark": "&#10003;", "checked": "&#9745;", "triangle": "&#9651;",
    "diamond": "&#9671;", "dagger": "&dagger;", "ddagger": "&Dagger;",
    "ast": "&lowast;", "oplus": "&oplus;", "otimes": "&otimes;",
    "degree": "&deg;", "angle": "&ang;", "perp": "&perp;", "sqrt": "&radic;",
}

MATH_FUNCTIONS = {
    "sin", "cos", "tan", "log", "ln", "exp", "min", "max", "lim", "arg",
    "det", "dim", "gcd", "sup", "inf", "mod",
}


def render_math(content: str, display: bool = False) -> str:
    """Render a LaTeX math fragment as inline HTML using entities and sup/sub."""
    body = _render_math_tokens(content)
    body = collapse(body)
    if display:
        return '<p class="display-math">%s</p>' % body
    return body


def _render_math_tokens(content: str) -> str:
    out = []
    index = 0
    length = len(content)
    while index < length:
        ch = content[index]
        if ch == "\\":
            match = re.match(r"\\([A-Za-z]+|.)", content[index:])
            if not match:
                index += 1
                continue
            name = match.group(1)
            index += match.end()
            if name == "frac":
                numerator, index = _read_math_group(content, index)
                denominator, index = _read_math_group(content, index)
                out.append("%s/%s" % (_wrap_math_fragment(numerator), _wrap_math_fragment(denominator)))
            elif name == "sqrt":
                radicand, index = _read_math_group(content, index)
                out.append("&radic;(%s)" % _render_math_tokens(radicand))
            elif name in ("text", "mathrm", "mathit", "mathbf", "operatorname", "mbox"):
                inner, index = _read_math_group(content, index)
                rendered = escape(inner)
                if name == "mathbf":
                    rendered = "<strong>%s</strong>" % rendered
                out.append(rendered)
            elif name in GREEK:
                out.append(GREEK[name])
            elif name in MATH_SYMBOLS:
                out.append(MATH_SYMBOLS[name])
            elif name in MATH_FUNCTIONS:
                out.append(name)
            elif name == "left" or name == "right":
                continue
            else:
                out.append(escape(name))
        elif ch in "^_":
            index += 1
            fragment, index = _read_math_group(content, index)
            tag = "sup" if ch == "^" else "sub"
            out.append("<%s>%s</%s>" % (tag, _render_math_tokens(fragment), tag))
        elif ch in "{}":
            index += 1
        elif ch.isalpha():
            match = re.match(r"[A-Za-z]+", content[index:])
            word = match.group(0)
            index += match.end()
            if word in MATH_FUNCTIONS:
                out.append(word)
            elif len(word) == 1:
                out.append("<em>%s</em>" % word)
            else:
                out.append(escape(word))
        else:
            out.append(escape(ch))
            index += 1
    return "".join(out)


def _wrap_math_fragment(fragment: str) -> str:
    rendered = _render_math_tokens(fragment)
    if len(re.sub(r"<[^>]+>", "", rendered)) > 1:
        return "(%s)" % rendered
    return rendered


def _read_math_group(content: str, index: int) -> tuple[str, int]:
    while index < len(content) and content[index] in " \t":
        index += 1
    if index >= len(content):
        return "", index
    if content[index] != "{":
        if content[index] == "\\":
            match = re.match(r"\\([A-Za-z]+|.)", content[index:])
            return content[index:index + match.end()], index + match.end()
        return content[index], index + 1
    depth = 0
    start = index + 1
    while index < len(content):
        if content[index] == "{":
            depth += 1
        elif content[index] == "}":
            depth -= 1
            if depth == 0:
                return content[start:index], index + 1
        index += 1
    return content[start:], index


class AcmReferenceFormatter:
    """Render BibTeX entries in ACM Reference Format as HTML list item content."""

    def format(self, entry: BibEntry) -> str:
        kind = entry.kind.lower()
        handler = {
            "article": self._article,
            "inproceedings": self._inproceedings,
            "conference": self._inproceedings,
            "proceedings": self._book,
            "incollection": self._incollection,
            "inbook": self._incollection,
            "book": self._book,
            "booklet": self._book,
            "techreport": self._techreport,
            "manual": self._techreport,
            "phdthesis": self._thesis,
            "mastersthesis": self._thesis,
            "misc": self._misc,
            "online": self._misc,
            "electronic": self._misc,
            "unpublished": self._misc,
        }.get(kind, self._misc)
        parts = [self._authors(entry), self._year(entry)]
        parts.extend(handler(entry))
        link = self._link(entry)
        if link:
            parts.append(link)
        return " ".join(part for part in parts if part)

    def sort_key(self, entry: BibEntry) -> tuple:
        names = parse_names(entry.get("author", "editor"))
        if names:
            primary = names[0].sort_key()
            others = tuple(name.sort_key() for name in names[1:])
        else:
            primary = (plain(entry.get("title")), "")
            others = ()
        return (primary, others, entry.get("year"), plain(entry.get("title")))

    def _authors(self, entry: BibEntry) -> str:
        names = parse_names(entry.get("author", "editor"))
        if not names:
            return "[n. a.]."
        rendered = [inline_latex(name.display()) for name in names]
        if len(rendered) == 1:
            joined = rendered[0]
        elif len(rendered) == 2:
            joined = "%s and %s" % (rendered[0], rendered[1])
        else:
            joined = "%s, and %s" % (", ".join(rendered[:-1]), rendered[-1])
        return joined.rstrip(".") + "."

    def _year(self, entry: BibEntry) -> str:
        year = strip_braces(entry.get("year", "date"))[:4]
        return ("%s." % year) if year else "[n. d.]."

    def _title(self, entry: BibEntry, italic: bool) -> str:
        title = inline_latex(entry.get("title"))
        if not title:
            return ""
        title = title.rstrip(".")
        suffix = "" if title.endswith(("?", "!")) else "."
        return ("<em>%s</em>%s" % (title, suffix)) if italic else (title + suffix)

    def _date(self, entry: BibEntry) -> str:
        year = strip_braces(entry.get("year"))[:4]
        month = MONTHS.get(strip_braces(entry.get("month")).lower()[:3]) or MONTHS.get(strip_braces(entry.get("month")))
        return " ".join(part for part in (month, year) if part)

    def _pages(self, entry: BibEntry) -> str:
        pages = strip_braces(entry.get("pages"))
        if not pages:
            return ""
        pages = re.sub(r"\s*-{2,}\s*", "-", pages)
        return re.sub(r"(?<=\d)\s*-\s*(?=\d)", "&ndash;", pages)

    def _publisher(self, entry: BibEntry) -> str:
        chunks = [inline_latex(entry.get("publisher", "institution", "organization", "school"))]
        chunks.append(inline_latex(entry.get("address", "location")))
        return ", ".join(chunk for chunk in chunks if chunk)

    def _link(self, entry: BibEntry) -> str:
        doi = strip_braces(entry.get("doi"))
        if doi:
            doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
            target = "https://doi.org/%s" % doi
        else:
            target = strip_braces(entry.get("url", "howpublished"))
            if not target.startswith("http"):
                return ""
        return '<a href="%s">%s</a>' % (escape_attr(target), escape(target))

    def _article(self, entry: BibEntry) -> list[str]:
        parts = [self._title(entry, italic=False)]
        journal = inline_latex(entry.get("journal", "journaltitle"))
        volume = strip_braces(entry.get("volume"))
        number = strip_braces(entry.get("number", "issue"))
        head = "<em>%s</em>" % journal if journal else ""
        numbering = ", ".join(part for part in (volume, number) if part)
        if numbering:
            head = ("%s %s" % (head, numbering)).strip()
        date = self._date(entry)
        if date:
            head = "%s (%s)" % (head, date)
        tail = self._pages(entry)
        articleno = strip_braces(entry.get("articleno"))
        if articleno:
            tail = "Article %s" % articleno
            numpages = strip_braces(entry.get("numpages"))
            if numpages:
                tail += ", %s pages" % numpages
        if tail:
            head = "%s, %s" % (head, tail) if head else tail
        if head:
            parts.append(head.strip() + ".")
        return parts

    def _inproceedings(self, entry: BibEntry) -> list[str]:
        parts = [self._title(entry, italic=False)]
        booktitle = inline_latex(entry.get("booktitle", "journal"))
        series = strip_braces(entry.get("series"))
        if booktitle:
            venue = "In <em>%s</em>" % booktitle
            if series:
                venue += " (%s)" % inline_latex(series)
            parts.append(venue + ".")
        trailer = [self._publisher(entry)]
        pages = self._pages(entry)
        articleno = strip_braces(entry.get("articleno"))
        if articleno:
            entryno = "Article %s" % articleno
            numpages = strip_braces(entry.get("numpages"))
            if numpages:
                entryno += ", %s pages" % numpages
            trailer.append(entryno)
        elif pages:
            trailer.append(pages)
        joined = ", ".join(chunk for chunk in trailer if chunk)
        if joined:
            parts.append(joined + ".")
        return parts

    def _incollection(self, entry: BibEntry) -> list[str]:
        return self._inproceedings(entry)

    def _book(self, entry: BibEntry) -> list[str]:
        parts = [self._title(entry, italic=True)]
        edition = strip_braces(entry.get("edition"))
        if edition:
            parts.append("%s edition." % inline_latex(edition))
        publisher = self._publisher(entry)
        pages = self._pages(entry)
        if pages:
            publisher = "%s, %s" % (publisher, pages) if publisher else pages
        if publisher:
            parts.append(publisher + ".")
        return parts

    def _techreport(self, entry: BibEntry) -> list[str]:
        parts = [self._title(entry, italic=True)]
        number = strip_braces(entry.get("number"))
        parts.append("Technical Report %s." % inline_latex(number) if number else "Technical Report.")
        publisher = self._publisher(entry)
        if publisher:
            parts.append(publisher + ".")
        return parts

    def _thesis(self, entry: BibEntry) -> list[str]:
        label = "Ph.D. Dissertation." if entry.kind.lower() == "phdthesis" else "Master's thesis."
        parts = [self._title(entry, italic=True), label]
        publisher = self._publisher(entry)
        if publisher:
            parts.append(publisher + ".")
        return parts

    def _misc(self, entry: BibEntry) -> list[str]:
        parts = [self._title(entry, italic=True)]
        note = inline_latex(entry.get("note", "howpublished"))
        if note and not note.startswith("http"):
            parts.append(note.rstrip(".") + ".")
        publisher = self._publisher(entry)
        if publisher:
            parts.append(publisher + ".")
        urldate = strip_braces(entry.get("urldate", "lastaccessed"))
        if urldate:
            parts.append("Retrieved %s from" % inline_latex(urldate))
        return parts


class Bibliography:
    """Assign ACM numbering to cited entries and render the reference list."""

    def __init__(self, entries: dict, formatter: AcmReferenceFormatter | None = None):
        self.entries = entries
        self.formatter = formatter or AcmReferenceFormatter()
        self.cited: list[str] = []
        self.numbers: dict[str, int] = {}
        self.missing: set[str] = set()

    def cite(self, key: str) -> None:
        key = key.strip()
        if not key:
            return
        if key not in self.entries:
            self.missing.add(key)
            return
        if key not in self.cited:
            self.cited.append(key)

    def finalise(self) -> None:
        ordered = sorted(self.cited, key=lambda key: self.formatter.sort_key(self.entries[key]))
        self.numbers = {key: index + 1 for index, key in enumerate(ordered)}
        self.cited = ordered

    def number(self, key: str) -> int | None:
        return self.numbers.get(key.strip())

    def render(self) -> list[str]:
        items = []
        for key in self.cited:
            items.append(
                '<li id="ref-%s">%s</li>' % (escape_attr(key), self.formatter.format(self.entries[key]))
            )
        return items


@dataclass
class Block:
    html: str
    kind: str = "block"
    level: int = 0
    numbered: bool = True
    anchor: str = ""
    css_class: str = ""


HIGHLIGHT_CLASS = "highlighted"

TEXT_TAGS = {
    "textit": "em",
    "emph": "em",
    "textbf": "strong",
    "underline": "u",
    "uline": "u",
    "texttt": "code",
    "textsuperscript": "sup",
    "textsubscript": "sub",
}


class HtmlConverter:
    """Convert parsed LaTeX nodes into the block and inline HTML of the paper body."""

    def __init__(
        self,
        bibliography: Bibliography,
        figures_dir: str = "./figures/",
        macros: dict | None = None,
        highlight_class: str = HIGHLIGHT_CLASS,
    ):
        self.bib = bibliography
        self.figures_dir = figures_dir
        self.macros = macros or {}
        self.highlight_class = highlight_class
        self.labels: dict[str, tuple[str, str]] = {}
        self.footnotes: list[str] = []
        self.warnings: list[str] = []
        self.figure_count = 0
        self.table_count = 0
        self.listing_count = 0
        self._pending = ("", "")
        self._counters = [0, 0, 0]
        self.in_appendix = False

    def collect_labels(self, nodes: Sequence) -> None:
        self.figure_count = 0
        self.table_count = 0
        self.listing_count = 0
        self._counters = [0, 0, 0]
        self._pending = ("", "")
        self.in_appendix = False
        self._collect(nodes)
        self.in_appendix = False
        self.figure_count = 0
        self.table_count = 0
        self.listing_count = 0
        self._counters = [0, 0, 0]

    def _collect(self, nodes: Sequence) -> None:
        for node in nodes:
            if isinstance(node, Command):
                if node.name == "appendix":
                    self.in_appendix = True
                    self._counters = [0, 0, 0]
                elif node.name in ("section", "subsection", "subsubsection") and not node.star:
                    number = self._advance_section(node.name)
                    title = collapse(node_text(node.args[0] if node.args else []))
                    self._pending = ("sec-" + slugify(title), number)
                elif node.name == "label" and node.args:
                    key = collapse(node_text(node.args[0]))
                    if key:
                        self.labels[key] = self._pending
                else:
                    for group in list(node.opts) + list(node.args):
                        self._collect(group)
            elif isinstance(node, Group):
                self._collect(node.nodes)
            elif isinstance(node, Environment):
                saved = self._pending
                if node.name in ("figure", "figure*", "wrapfigure"):
                    self.figure_count += 1
                    self._pending = ("fig-%d" % self.figure_count, str(self.figure_count))
                elif node.name in ("table", "table*"):
                    self.table_count += 1
                    self._pending = ("tab-%d" % self.table_count, str(self.table_count))
                elif node.name in ("lstlisting", "listing", "algorithm"):
                    self.listing_count += 1
                    self._pending = ("lst-%d" % self.listing_count, str(self.listing_count))
                self._collect(node.body)
                self._pending = saved

    def _advance_section(self, name: str) -> str:
        depth = {"section": 0, "subsection": 1, "subsubsection": 2}[name]
        self._counters[depth] += 1
        for index in range(depth + 1, len(self._counters)):
            self._counters[index] = 0
        parts = [str(value) for value in self._counters[: depth + 1]]
        if self.in_appendix:
            parts[0] = chr(ord("A") + self._counters[0] - 1)
        return ".".join(parts)

    def convert_blocks(self, nodes: Sequence) -> list[Block]:
        blocks: list[Block] = []
        buffer: list[str] = []

        def flush() -> None:
            text = collapse("".join(buffer))
            text = re.sub(r"^(?:<br>\s*)+|(?:<br>\s*)+$", "", text)
            buffer.clear()
            if text:
                blocks.append(Block("<p>%s</p>" % text))

        for node in nodes:
            if isinstance(node, ParagraphBreak):
                flush()
            elif isinstance(node, Command) and node.name in ("section", "subsection", "subsubsection", "paragraph", "subparagraph"):
                flush()
                blocks.append(self._heading(node))
            elif isinstance(node, Command) and node.name in ("bibliography", "bibliographystyle", "printbibliography", "maketitle"):
                flush()
            elif isinstance(node, Command) and node.name in METADATA_COMMANDS:
                flush()
            elif isinstance(node, Command) and node.name == "appendix":
                flush()
                self.in_appendix = True
                self._counters = [0, 0, 0]
            elif isinstance(node, Command) and node.name == "rule":
                flush()
                blocks.append(Block("<hr>"))
            elif isinstance(node, Verbatim) and node.name in DROPPED_ENVIRONMENTS:
                flush()
            elif isinstance(node, Command) and node.name in ("resizebox", "scalebox", "adjustbox", "parbox", "makebox") and node.args:
                flush()
                blocks.extend(self.convert_blocks(node.args[-1]))
            elif isinstance(node, Environment) and self._is_block_environment(node.name):
                flush()
                blocks.extend(self._environment_blocks(node))
            elif isinstance(node, Verbatim) and node.name in VERBATIM_ENVIRONMENTS:
                flush()
                blocks.append(self._listing(node))
            elif isinstance(node, Group) and self._holds_blocks(node.nodes):
                flush()
                blocks.extend(self.convert_blocks(node.nodes))
            elif isinstance(node, Math) and node.display:
                flush()
                blocks.append(Block(render_math(node.content, display=True)))
            else:
                buffer.append(self.inline([node]))
        flush()
        return blocks

    def _holds_blocks(self, nodes: Sequence) -> bool:
        """Report whether a brace group wraps block content, such as a float, rather than inline text."""
        for node in nodes:
            if isinstance(node, Environment) and self._is_block_environment(node.name):
                return True
            if isinstance(node, Verbatim) and node.name in VERBATIM_ENVIRONMENTS:
                return True
            if isinstance(node, Group) and self._holds_blocks(node.nodes):
                return True
        return False

    @staticmethod
    def _is_block_environment(name: str) -> bool:
        return name in {
            "figure", "figure*", "wrapfigure", "table", "table*", "itemize",
            "enumerate", "description", "quote", "quotation", "verse", "center",
            "acks", "abstract", "tabular", "tabular*", "tabularx", "algorithm",
            "listing", "subfigure", "minipage",
        }

    def _heading(self, node: Command) -> Block:
        level = {"section": 2, "subsection": 3, "subsubsection": 4, "paragraph": 4, "subparagraph": 4}[node.name]
        title = self.inline(node.args[0]) if node.args else ""
        anchor = "sec-" + slugify(collapse(node_text(node.args[0] if node.args else [])))
        numbered = not node.star and node.name in ("section", "subsection", "subsubsection")
        html = "<h%d>%s</h%d>" % (level, collapse(title), level)
        css_class = ""
        if numbered:
            css_class = "appendix" if self.in_appendix else "numbered"
        return Block(html, kind="heading", level=level, numbered=numbered, anchor=anchor, css_class=css_class)

    def _environment_blocks(self, env: Environment) -> list[Block]:
        name = env.name
        if name in ("figure", "figure*", "wrapfigure"):
            return [self._figure(env)]
        if name in ("table", "table*"):
            return [self._table_float(env)]
        if name in ("tabular", "tabular*", "tabularx"):
            return [Block(self._tabular(env, caption="", anchor=""))]
        if name in ("itemize", "enumerate", "description"):
            return [Block(self._list(env))]
        if name in ("quote", "quotation", "verse"):
            inner = self.convert_blocks(env.body)
            body = "\n".join(block.html for block in inner)
            return [Block("<blockquote>\n%s\n</blockquote>" % indent(body, 1))]
        if name == "acks":
            heading = Block("<h2>Acknowledgements</h2>", kind="heading", level=2, numbered=False)
            return [heading] + self.convert_blocks(env.body)
        if name == "abstract":
            return self.convert_blocks(env.body)
        if name in ("algorithm", "listing"):
            return self.convert_blocks(env.body)
        return self.convert_blocks(env.body)

    def _figure(self, env: Environment) -> Block:
        self.figure_count += 1
        number = self.figure_count
        images = list(iter_commands(env.body, "includegraphics"))
        caption = self._first_argument(env.body, "caption")
        description = self._first_argument(env.body, "Description")
        lines = ['<figure id="fig-%d">' % number]
        alt = collapse(self.inline(description)) if description else ""
        alt = re.sub(r"<[^>]+>", "", alt)
        if not description:
            self.warnings.append("figure %d has no \\Description" % number)
        for image in images:
            source = self.figure_path(collapse(node_text(image.args[0])) if image.args else "")
            lines.append('\t<img src="%s" alt="%s">' % (escape_attr(source), escape_attr(alt)))
        if caption:
            lines.append(
                "\t<figcaption><strong>Figure %d:</strong> %s</figcaption>" % (number, collapse(self.inline(caption)))
            )
        lines.append("</figure>")
        return Block("\n".join(lines))

    def _table_float(self, env: Environment) -> Block:
        self.table_count += 1
        number = self.table_count
        caption = self._first_argument(env.body, "caption")
        caption_html = collapse(self.inline(caption)) if caption else ""
        tabular = find_environment(env.body, "tabular", "tabular*", "tabularx")
        if tabular is None:
            return Block("\n".join(block.html for block in self.convert_blocks(env.body)))
        return Block(self._tabular(tabular, caption_html, "tab-%d" % number, number))

    def _tabular(self, env: Environment, caption: str, anchor: str, number: int | None = None) -> str:
        spec = node_text(env.args[-1]) if env.args else ""
        columns = self._column_count(spec)
        head_rows, body_rows = self._split_rows(env.body)
        self._rowspans: dict[int, int] = {}
        lines = []
        if anchor:
            lines.append(
                '<div class="table-wrap" role="region" aria-labelledby="%s-caption" tabindex="0">' % anchor
            )
            lines.append('\t<table id="%s">' % anchor)
        else:
            lines.append('<div class="table-wrap" tabindex="0">')
            lines.append("\t<table>")
        if caption:
            label = "<strong>Table %d:</strong> " % number if number else ""
            caption_id = ' id="%s-caption"' % anchor if anchor else ""
            lines.append("\t\t<caption%s>%s%s</caption>" % (caption_id, label, caption))
        if head_rows:
            lines.append("\t\t<thead>")
            for row in head_rows:
                lines.extend(self._render_row(row, "th", columns, indent_level=3))
            lines.append("\t\t</thead>")
        lines.append("\t\t<tbody>")
        for row in body_rows:
            lines.extend(self._render_row(row, "td", columns, indent_level=3))
        lines.append("\t\t</tbody>")
        lines.append("\t</table>")
        lines.append("</div>")
        return "\n".join(lines)

    @staticmethod
    def _column_count(spec: str) -> int:
        cleaned = re.sub(r"[|@!>]\s*\{[^{}]*\}", "", spec)
        cleaned = re.sub(r"\{[^{}]*\}", "", cleaned)
        return max(1, len(re.findall(r"[lcrpXmb]", cleaned)))

    def _split_rows(self, nodes: Sequence) -> tuple[list[list], list[list]]:
        rows, header_end = self._rows(nodes)
        if header_end is None:
            return [], rows
        return rows[:header_end], rows[header_end:]

    def _rows(self, nodes: Sequence) -> tuple[list[list], int | None]:
        """Split the body of a tabular into rows, returning where any header ends."""
        rows: list[list] = []
        current: list = []
        separators: list[int] = []
        leading: list[str] = []
        rules = ("midrule", "hline", "cmidrule", "toprule", "bottomrule")
        for node in self._expand_macros(nodes):
            if isinstance(node, Command) and node.name == "\\":
                rows.append(current)
                current = []
                continue
            if isinstance(node, Command) and node.name in rules:
                if not rows:
                    leading.append(node.name)
                elif node.name in ("midrule", "hline") and (not separators or separators[-1] != len(rows)):
                    separators.append(len(rows))
                continue
            if isinstance(node, ParagraphBreak):
                continue
            current.append(node)
        rows.append(current)
        rows = [row for row in rows if self._row_has_content(row)]
        internal = [position for position in separators if 0 < position < len(rows)]
        if "toprule" in leading or not (leading or separators):
            return rows, (internal[0] if internal else (1 if len(rows) > 1 else None))
        return rows, None

    def _expand_macros(self, nodes: Sequence) -> list:
        """Replace user macro calls with their bodies so rules and colours inside them are recognised."""
        out: list = []
        for node in nodes:
            if isinstance(node, Command) and node.name in self.macros and not node.args:
                count, body = self.macros[node.name]
                if body and not count:
                    parser = LatexParser(body)
                    parser.macros = {key: value for key, value in self.macros.items() if key != node.name}
                    out.extend(self._expand_macros(parser.parse()))
                    continue
            out.append(node)
        return out

    def _row_has_content(self, row: Sequence) -> bool:
        for item in row:
            if isinstance(item, Text):
                if item.value.strip().strip("&"):
                    return True
            elif isinstance(item, Command):
                if collapse(self._command(item)):
                    return True
            else:
                return True
        return False

    def _render_row(self, row: Sequence, tag: str, columns: int, indent_level: int) -> list[str]:
        cells = self._split_cells(row)
        pad = "\t" * indent_level
        lines = [pad + "<tr>"]
        pending = getattr(self, "_rowspans", {})
        column = 0
        index = 0
        while index < len(cells):
            if pending.get(column):
                pending[column] -= 1
                if not collapse(node_text(cells[index])):
                    index += 1
                column += 1
                continue
            content, colspan, rowspan, highlighted = self._cell_content(cells[index])
            index += 1
            if rowspan > 1:
                pending[column] = rowspan - 1
            attributes = ""
            if highlighted:
                attributes += ' class="%s"' % escape_attr(self.highlight_class)
            if colspan > 1:
                attributes += ' colspan="%d"' % colspan
            if rowspan > 1:
                attributes += ' rowspan="%d"' % rowspan
            if tag == "th":
                content = re.sub(r"^<strong>(.*)</strong>$", r"\1", content)
            scope = ' scope="col"' if tag == "th" else ""
            lines.append("%s\t<%s%s%s>%s</%s>" % (pad, tag, scope, attributes, content, tag))
            column += colspan
        lines.append(pad + "</tr>")
        return lines

    @staticmethod
    def _split_cells(row: Sequence) -> list[list]:
        cells: list[list] = [[]]
        for node in row:
            if isinstance(node, Text) and "&" in node.value:
                pieces = node.value.split("&")
                for index, piece in enumerate(pieces):
                    if index:
                        cells.append([])
                    if piece:
                        cells[-1].append(Text(piece))
            else:
                cells[-1].append(node)
        return cells

    def _cell_content(self, cell: Sequence) -> tuple[str, int, int, bool]:
        colspan = 1
        rowspan = 1
        highlighted = any(
            isinstance(node, Command) and node.name in ("cellcolor", "rowcolor") for node in cell
        )
        nodes = [node for node in cell if not (isinstance(node, Text) and not node.value.strip())]
        nodes = [node for node in nodes if not (isinstance(node, Command) and node.name in ("cellcolor", "rowcolor"))]
        for _ in range(2):
            if len(nodes) != 1 or not isinstance(nodes[0], Command):
                break
            command = nodes[0]
            if command.name == "multicolumn" and len(command.args) > 2:
                colspan = to_int(node_text(command.args[0]), 1)
                nodes = command.args[2]
            elif command.name == "multirow" and len(command.args) > 2:
                rowspan = to_int(node_text(command.args[0]), 1)
                nodes = command.args[2]
            else:
                break
            nodes = [node for node in nodes if not (isinstance(node, Text) and not node.value.strip())]
        return collapse(self.inline(nodes)), colspan, rowspan, highlighted

    def _inline_tabular(self, env: Environment) -> str:
        """Render a tabular nested inside a cell: line breaks for one column, a plain table otherwise."""
        rows, _ = self._rows(env.body)
        columns = self._column_count(node_text(env.args[-1]) if env.args else "")
        if columns <= 1:
            lines = []
            for row in rows:
                text = " ".join(
                    collapse(self.inline(cell)) for cell in self._split_cells(row)
                )
                text = collapse(text)
                if text:
                    lines.append(text)
            return "<br>".join(lines)
        out = ["<table>", "<tbody>"]
        for row in rows:
            out.append("<tr>")
            for cell in self._split_cells(row):
                content, colspan, rowspan, highlighted = self._cell_content(cell)
                attributes = ' class="%s"' % escape_attr(self.highlight_class) if highlighted else ""
                attributes += ' colspan="%d"' % colspan if colspan > 1 else ""
                attributes += ' rowspan="%d"' % rowspan if rowspan > 1 else ""
                out.append("<td%s>%s</td>" % (attributes, content))
            out.append("</tr>")
        out.extend(["</tbody>", "</table>"])
        return "".join(out)

    def _list(self, env: Environment) -> str:
        items: list[list] = []
        labels: list[str] = []
        current: list | None = None
        for node in env.body:
            if isinstance(node, Command) and node.name == "item":
                current = []
                items.append(current)
                labels.append(collapse(self.inline(node.opts[0])) if node.opts else "")
                continue
            if current is None:
                continue
            current.append(node)
        if env.name == "description":
            lines = ["<dl>"]
            for label, item in zip(labels, items):
                lines.append("\t<dt>%s</dt>" % label)
                lines.append("\t<dd>%s</dd>" % self._item_html(item))
            lines.append("</dl>")
            return "\n".join(lines)
        tag = "ol" if env.name == "enumerate" else "ul"
        lines = ["<%s>" % tag]
        for label, item in zip(labels, items):
            content = self._item_html(item)
            if label and tag == "ul":
                content = "%s %s" % (label, content)
            lines.append("\t<li>%s</li>" % content)
        lines.append("</%s>" % tag)
        return "\n".join(lines)

    def _item_html(self, nodes: Sequence) -> str:
        blocks = self.convert_blocks(nodes)
        if len(blocks) == 1 and blocks[0].html.startswith("<p>") and blocks[0].html.endswith("</p>"):
            return blocks[0].html[3:-4]
        return "\n" + indent("\n".join(block.html for block in blocks), 2) + "\n\t"

    def _listing(self, node: Verbatim) -> Block:
        language = ' class="language-%s"' % node.language if node.language else ""
        return Block("<pre><code%s>%s</code></pre>" % (language, escape(node.content)))

    @staticmethod
    def _first_argument(nodes: Sequence, name: str) -> list | None:
        for command in iter_commands(nodes, name):
            if command.args:
                return command.args[-1]
        return None

    def figure_path(self, source: str) -> str:
        return self.figures_dir + os.path.basename(source.strip())

    def inline(self, nodes: Sequence) -> str:
        out = []
        for node in nodes:
            if isinstance(node, Text):
                out.append(escape(typographic(node.value)))
            elif isinstance(node, ParagraphBreak):
                out.append(" ")
            elif isinstance(node, Group):
                out.append(self.inline(node.nodes))
            elif isinstance(node, Math):
                out.append(render_math(node.content, display=False))
            elif isinstance(node, Verbatim):
                if node.name not in DROPPED_ENVIRONMENTS:
                    out.append("<code>%s</code>" % escape(node.content))
            elif isinstance(node, Environment):
                if node.name in ("tabular", "tabular*", "tabularx", "array"):
                    out.append(self._inline_tabular(node))
                else:
                    out.append("\n".join(block.html for block in self._environment_blocks(node)))
            elif isinstance(node, Command):
                out.append(self._command(node))
        return "".join(out)

    def _command(self, node: Command) -> str:
        name = node.name
        if name in TEXT_TAGS:
            tag = TEXT_TAGS[name]
            return "<%s>%s</%s>" % (tag, self.inline(node.args[0]) if node.args else "", tag)
        if name == "textsc":
            return self.inline(node.args[0]) if node.args else ""
        if name in ("textrm", "textnormal", "textsf", "mbox", "text", "makecell"):
            return self.inline(node.args[0]) if node.args else ""
        if name == "thead":
            return re.sub(r"<br>\s*", "<br>", self.inline(node.args[0])) if node.args else ""
        if name in ("\\", "newline", "linebreak", "cr"):
            return "<br>"
        if name in ("cite", "citep", "citet"):
            return self._citation(node)
        if name in ("ref", "autoref", "eqref", "pageref"):
            return self._reference(node)
        if name == "label":
            return ""
        if name == "footnote":
            return self._footnote(node)
        if name == "url":
            target = collapse(node_text(node.args[0])) if node.args else ""
            return '<a href="%s">%s</a>' % (escape_attr(target), escape(target))
        if name == "href":
            target = collapse(node_text(node.args[0])) if node.args else ""
            text = self.inline(node.args[1]) if len(node.args) > 1 else escape(target)
            return '<a href="%s">%s</a>' % (escape_attr(target), text)
        if name == "includegraphics":
            source = self.figure_path(collapse(node_text(node.args[0])) if node.args else "")
            return '<img src="%s" alt="">' % escape_attr(source)
        if name in ("resizebox", "scalebox"):
            return self.inline(node.args[-1]) if node.args else ""
        if name in ("fcolorbox", "colorbox", "fbox", "framebox"):
            content = collapse(self.inline(node.args[-1])) if node.args else ""
            return '<span class="boxed">%s</span>' % content if content else ""
        if name == "textcolor":
            return self.inline(node.args[-1]) if node.args else ""
        if name in ACCENT_COMMANDS and node.args:
            base = node_text(node.args[0])
            return escape(apply_accent(base, ACCENT_COMMANDS[name]))
        if name in SYMBOL_COMMANDS:
            return escape(SYMBOL_COMMANDS[name])
        if name in IGNORED_COMMANDS or name in TEX_REGISTERS:
            return ""
        if name in self.macros:
            return self._expand_macro(node)
        if node.args:
            return self.inline(node.args[-1])
        self.warnings.append("unhandled command \\%s" % name)
        return ""

    def _expand_macro(self, node: Command) -> str:
        count, body = self.macros[node.name]
        if not body:
            return self.inline(node.args[-1]) if node.args else ""
        for index in range(count):
            replacement = raw_latex(node.args[index]) if index < len(node.args) else ""
            body = body.replace("#%d" % (index + 1), replacement)
        expanded = LatexParser(body)
        expanded.macros = {key: value for key, value in self.macros.items() if key != node.name}
        return self.inline(expanded.parse())

    def _citation(self, node: Command) -> str:
        keys = [key.strip() for key in collapse(node_text(node.args[0] if node.args else [])).split(",")]
        rendered = []
        for key in keys:
            self.bib.cite(key)
            number = self.bib.number(key)
            if number is None:
                self.warnings.append("missing bibliography entry %s" % key)
                rendered.append((10 ** 6, '<a href="#ref-%s">?</a>' % escape_attr(key)))
            else:
                rendered.append((number, '<a href="#ref-%s">%d</a>' % (escape_attr(key), number)))
        rendered.sort(key=lambda item: item[0])
        body = ", ".join(item[1] for item in rendered)
        if node.opts:
            note = collapse(self.inline(node.opts[-1]))
            if note:
                body = "%s, %s" % (body, note)
        return "[%s]" % body

    def _reference(self, node: Command) -> str:
        key = collapse(node_text(node.args[0])) if node.args else ""
        target = self.labels.get(key)
        if not target or not target[0]:
            self.warnings.append("unresolved reference %s" % key)
            return "??"
        anchor, number = target
        return '<a href="#%s">%s</a>' % (escape_attr(anchor), escape(number))

    def _footnote(self, node: Command) -> str:
        content = collapse(self.inline(node.args[0])) if node.args else ""
        number = len(self.footnotes) + 1
        self.footnotes.append(content)
        return '<sup id="fnref-%d"><a href="#fn-%d" aria-label="Footnote %d">%d</a></sup>' % (
            number, number, number, number,
        )


def typographic(text: str) -> str:
    text = text.replace("``", "\u201c").replace("''", "\u201d")
    text = text.replace("---", "\u2014").replace("--", "\u2013")
    text = re.sub(r"`(?=[^`])", "\u2018", text)
    text = text.replace("'", "\u2019")
    text = text.replace("~", " ")
    return re.sub(r"[ \t\n]+", " ", text)


def apply_accent(base: str, combining: str) -> str:
    import unicodedata

    base = base.strip() or " "
    return unicodedata.normalize("NFC", base[0] + combining + base[1:])


def node_text(nodes: Sequence) -> str:
    out = []
    for node in nodes:
        if isinstance(node, Text):
            out.append(node.value)
        elif isinstance(node, Group):
            out.append(node_text(node.nodes))
        elif isinstance(node, Verbatim):
            out.append(node.content)
        elif isinstance(node, Math):
            out.append(node.content)
        elif isinstance(node, Command):
            if node.name in SYMBOL_COMMANDS:
                out.append(SYMBOL_COMMANDS[node.name])
            for group in node.args:
                out.append(node_text(group))
    return "".join(out)


def raw_latex(nodes: Sequence) -> str:
    """Reconstruct approximate LaTeX source, used when expanding user macros."""
    out = []
    for node in nodes:
        if isinstance(node, Text):
            out.append(node.value)
        elif isinstance(node, Group):
            out.append("{%s}" % raw_latex(node.nodes))
        elif isinstance(node, Math):
            out.append("$%s$" % node.content)
        elif isinstance(node, Verbatim):
            out.append(node.content)
        elif isinstance(node, ParagraphBreak):
            out.append("\n\n")
        elif isinstance(node, Environment):
            out.append("\\begin{%s}%s\\end{%s}" % (node.name, raw_latex(node.body), node.name))
        elif isinstance(node, Command):
            out.append("\\" + node.name)
            for group in node.opts:
                out.append("[%s]" % raw_latex(group))
            for group in node.args:
                out.append("{%s}" % raw_latex(group))
    return "".join(out)


def to_int(value: str, fallback: int) -> int:
    match = re.search(r"\d+", value or "")
    return int(match.group(0)) if match else fallback


def indent(text: str, level: int) -> str:
    """Indent block markup, leaving the contents of pre elements untouched."""
    prefix = "\t" * level
    lines = []
    preformatted = False
    for line in text.split("\n"):
        lines.append(line if preformatted or not line.strip() else prefix + line)
        opened = line.count("<pre")
        closed = line.count("</pre>")
        if opened > closed:
            preformatted = True
        elif closed >= opened and closed:
            preformatted = False
    return "\n".join(lines)


def inline_latex(source: str) -> str:
    """Convert a short LaTeX fragment, such as a BibTeX field, into inline HTML."""
    if not source:
        return ""
    parser = LatexParser(source)
    nodes = parser.parse()
    converter = HtmlConverter(Bibliography({}), macros=parser.macros)
    return collapse(converter.inline(nodes))


@dataclass
class Author:
    name: str = ""
    affiliation: str = ""
    email: str = ""
    orcid: str = ""


@dataclass
class Metadata:
    title: str = ""
    subtitle: str = ""
    authors: list = field(default_factory=list)
    booktitle: str = ""
    doi: str = ""
    ccs: list = field(default_factory=list)
    keywords: list = field(default_factory=list)


def walk(nodes: Iterable):
    for node in nodes:
        yield node
        if isinstance(node, Group):
            yield from walk(node.nodes)
        elif isinstance(node, Environment):
            yield from walk(list(node.args) + list(node.opts))
            yield from walk(node.body)
        elif isinstance(node, Command):
            yield from walk([item for group in list(node.opts) + list(node.args) for item in group])


class PaperBuilder:
    """Assemble the final HTML document from preamble metadata and body blocks."""

    def __init__(self, converter: HtmlConverter, bibliography: Bibliography, css: str, language: str):
        self.converter = converter
        self.bib = bibliography
        self.css = css
        self.language = language

    def metadata(self, preamble: Sequence) -> Metadata:
        meta = Metadata()
        current: Author | None = None
        for node in preamble:
            if not isinstance(node, Command):
                continue
            if node.name == "title" and node.args:
                meta.title = collapse(self.converter.inline(node.args[-1]))
            elif node.name == "subtitle" and node.args:
                meta.subtitle = collapse(self.converter.inline(node.args[-1]))
            elif node.name == "author" and node.args:
                current = Author(name=collapse(self.converter.inline(node.args[-1])))
                meta.authors.append(current)
            elif node.name == "affiliation" and node.args and current is not None:
                current.affiliation = self._affiliation(node.args[-1])
            elif node.name == "email" and node.args and current is not None:
                current.email = collapse(node_text(node.args[-1]))
            elif node.name == "orcid" and node.args and current is not None:
                current.orcid = collapse(node_text(node.args[-1]))
            elif node.name == "acmBooktitle" and node.args:
                meta.booktitle = collapse(self.converter.inline(node.args[-1]))
            elif node.name == "acmConference" and node.args and not meta.booktitle:
                meta.booktitle = ", ".join(
                    collapse(self.converter.inline(group)) for group in node.args
                )
            elif node.name == "acmDOI" and node.args:
                meta.doi = collapse(node_text(node.args[-1]))
            elif node.name == "ccsdesc" and node.args:
                concept = collapse(node_text(node.args[-1])).replace("~", ": ")
                meta.ccs.append(escape(concept))
            elif node.name == "keywords" and node.args:
                keywords = collapse(self.converter.inline(node.args[-1]))
                meta.keywords = [part.strip() for part in keywords.split(",") if part.strip()]
        return meta

    def _affiliation(self, nodes: Sequence) -> str:
        parts: list[str] = []
        for command in ("department", "institution", "city", "state", "postcode", "country"):
            for found in iter_commands(nodes, command):
                if not found.args:
                    continue
                value = collapse(self.converter.inline(found.args[-1]))
                value = re.sub(r"<br>\s*", ", ", value)
                if value:
                    parts.append(value)
        return ", ".join(parts)

    def header(self, meta: Metadata) -> list[str]:
        lines = ["<header>"]
        title = meta.title + (": " + meta.subtitle if meta.subtitle else "")
        lines.append("\t<h1>%s</h1>" % title)
        if meta.authors:
            lines.append('\t<section aria-label="Authors">')
            lines.append("\t\t<h2>Authors</h2>")
            lines.append("\t\t<ul>")
            for author in meta.authors:
                text = author.name
                if author.affiliation:
                    text += ", " + author.affiliation
                if author.email:
                    text += '. <a href="mailto:%s">%s</a>' % (escape_attr(author.email), escape(author.email))
                if author.orcid:
                    identifier = re.sub(r"^https?://orcid\.org/", "", author.orcid)
                    text += '. ORCID: <a href="https://orcid.org/%s">%s</a>' % (
                        escape_attr(identifier), escape(identifier),
                    )
                lines.append("\t\t\t<li>%s</li>" % text)
            lines.append("\t\t</ul>")
            lines.append("\t</section>")
        if meta.booktitle:
            lines.append("\t<p>%s</p>" % meta.booktitle)
        if meta.doi:
            url = "https://doi.org/%s" % meta.doi
            lines.append('\t<p>DOI: <a href="%s">%s</a></p>' % (escape_attr(url), escape(url)))
        lines.append("</header>")
        return lines

    def front_sections(self, meta: Metadata, abstract: Sequence | None) -> list[str]:
        lines: list[str] = []
        if abstract is not None:
            body = self.converter.convert_blocks(abstract)
            lines.append("<section>")
            lines.append("\t<h2>Abstract</h2>")
            lines.append(indent("\n".join(block.html for block in body), 1))
            lines.append("</section>")
        if meta.ccs:
            lines.append("<section>")
            lines.append("\t<h2>CCS Concepts</h2>")
            for concept in meta.ccs:
                lines.append("\t<p>%s</p>" % concept)
            lines.append("</section>")
        if meta.keywords:
            lines.append("<section>")
            lines.append("\t<h2>Keywords</h2>")
            lines.append("\t<ul>")
            for keyword in meta.keywords:
                lines.append("\t\t<li>%s</li>" % keyword)
            lines.append("\t</ul>")
            lines.append("</section>")
        return lines

    def body_sections(self, blocks: Sequence[Block]) -> list[str]:
        anchors = {anchor for anchor, _ in self.converter.labels.values() if anchor}
        lines: list[str] = []
        open_section = False
        for block in blocks:
            if block.kind == "heading" and block.level == 2:
                if open_section:
                    lines.append("</section>")
                attributes = ' class="%s"' % escape_attr(block.css_class) if block.css_class else ""
                lines.append("<section%s>" % attributes)
                open_section = True
                lines.append(indent(self._with_anchor(block, anchors), 1))
                continue
            if not open_section:
                lines.append("<section>")
                open_section = True
            html = self._with_anchor(block, anchors) if block.kind == "heading" else block.html
            lines.append(indent(html, 1))
        if open_section:
            lines.append("</section>")
        return lines

    @staticmethod
    def _with_anchor(block: Block, anchors: set) -> str:
        if block.anchor and block.anchor in anchors:
            return block.html.replace(">", ' id="%s">' % escape_attr(block.anchor), 1)
        return block.html

    def footnotes(self) -> list[str]:
        if not self.converter.footnotes:
            return []
        lines = ['<section id="footnotes">', "\t<h2>Notes</h2>", "\t<ol>"]
        for index, content in enumerate(self.converter.footnotes, start=1):
            back = '<a href="#fnref-%d" aria-label="Back to text, footnote %d">Back to text</a>' % (index, index)
            lines.append('\t\t<li id="fn-%d">%s %s</li>' % (index, content, back))
        lines.append("\t</ol>")
        lines.append("</section>")
        return lines

    def references(self) -> list[str]:
        items = self.bib.render()
        if not items:
            return []
        lines = ['<section id="references">', "\t<h2>References</h2>", "\t<ol>"]
        for item in items:
            lines.append("\t\t" + item)
        lines.append("\t</ol>")
        lines.append("</section>")
        return lines

    def build(self, meta: Metadata, abstract: Sequence | None, blocks: Sequence[Block]) -> str:
        article: list[str] = []
        article.extend(self.header(meta))
        article.extend(self.front_sections(meta, abstract))
        article.extend(self.body_sections(blocks))
        article.extend(self.footnotes())
        article.extend(self.references())
        document = [
            "<!DOCTYPE html>",
            '<html lang="%s">' % escape_attr(self.language),
            "",
            "<head>",
            '\t<meta charset="utf-8">',
            '\t<meta name="viewport" content="width=device-width, initial-scale=1">',
            '\t<meta name="color-scheme" content="light dark">',
            "\t<title>%s</title>" % (meta.title or "Paper"),
            '\t<link rel="stylesheet" href="%s">' % escape_attr(self.css),
            "</head>",
            "",
            "<body>",
            '\t<a class="skip-link" href="#content">Skip to main content</a>',
            '\t<main id="content">',
            "\t\t<article>",
            indent("\n".join(article), 3),
            "\t\t</article>",
            "\t</main>",
            "</body>",
            "",
            "</html>",
            "",
        ]
        return "\n".join(document)


def load_source(path: str, seen: set | None = None) -> str:
    """Read a .tex file, inlining any \\input or \\include files it references."""
    seen = seen if seen is not None else set()
    real = os.path.abspath(path)
    if real in seen:
        return ""
    seen.add(real)
    with open(real, encoding="utf-8") as handle:
        text = LatexParser._strip_comments(handle.read())
    base = os.path.dirname(real)

    def replace(match: re.Match) -> str:
        name = match.group(1).strip()
        candidate = os.path.join(base, name if name.endswith(".tex") else name + ".tex")
        return load_source(candidate, seen) if os.path.exists(candidate) else ""

    return re.sub(r"\\(?:input|include)\s*\{([^{}]+)\}", replace, text)


def resolve_bib_path(tex_path: str, nodes: Sequence, explicit: str | None) -> str | None:
    if explicit:
        return explicit
    base = os.path.dirname(os.path.abspath(tex_path))
    for command in iter_commands(nodes, "bibliography"):
        for name in collapse(node_text(command.args[0] if command.args else [])).split(","):
            name = name.strip()
            if not name:
                continue
            candidate = os.path.join(base, name if name.endswith(".bib") else name + ".bib")
            if os.path.exists(candidate):
                return candidate
    fallback = os.path.join(base, "references.bib")
    return fallback if os.path.exists(fallback) else None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert an acmart LaTeX paper into HTML.")
    parser.add_argument("tex", help="path to the main .tex file")
    parser.add_argument("-b", "--bib", help="path to the .bib file (default: taken from \\bibliography)")
    parser.add_argument("-o", "--output", help="path of the HTML file to write (default: alongside the .tex)")
    parser.add_argument("--css", default="../papers.css", help="href of the stylesheet")
    parser.add_argument("--figures", default="./figures/", help="directory prefix used for image sources")
    parser.add_argument(
        "--highlight-class",
        default=HIGHLIGHT_CLASS,
        help="class applied to table cells shaded with \\cellcolor or \\rowcolor",
    )
    parser.add_argument("--lang", default="en", help="value of the html lang attribute")
    parser.add_argument("--quiet", action="store_true", help="suppress conversion warnings")
    args = parser.parse_args(argv)

    latex = LatexParser(load_source(args.tex))
    nodes = latex.parse()
    document = find_environment(nodes, "document")
    body = document.body if document else nodes
    preamble = nodes if document is None else [node for node in nodes if node is not document]

    entries: dict = {}
    bib_path = resolve_bib_path(args.tex, nodes, args.bib)
    if bib_path and os.path.exists(bib_path):
        with open(bib_path, encoding="utf-8") as handle:
            entries = BibParser(handle.read()).parse()
    elif not args.quiet:
        print("warning: no .bib file found, references will be empty", file=sys.stderr)

    bibliography = Bibliography(entries)
    for node in walk(nodes):
        if isinstance(node, Command) and node.name in ("cite", "citep", "citet", "nocite"):
            for key in collapse(node_text(node.args[0] if node.args else [])).split(","):
                if key.strip() == "*":
                    for entry_key in entries:
                        bibliography.cite(entry_key)
                else:
                    bibliography.cite(key)
    bibliography.finalise()

    converter = HtmlConverter(
        bibliography,
        figures_dir=args.figures,
        macros=latex.macros,
        highlight_class=args.highlight_class,
    )
    converter.collect_labels(body)

    abstract_env = find_environment(nodes, "abstract")
    abstract = abstract_env.body if abstract_env else None
    body = [node for node in body if not (isinstance(node, Environment) and node.name == "abstract")]

    builder = PaperBuilder(converter, bibliography, args.css, args.lang)
    meta = builder.metadata(list(walk(preamble)) + list(walk(body)))
    blocks = converter.convert_blocks(body)
    html = builder.build(meta, abstract, blocks)

    output = args.output or os.path.splitext(args.tex)[0] + ".html"
    with open(output, "w", encoding="ascii", errors="xmlcharrefreplace") as handle:
        handle.write(html)

    if not args.quiet:
        for warning in dict.fromkeys(converter.warnings):
            print("warning: %s" % warning, file=sys.stderr)
        if bibliography.missing:
            print("warning: uncited or unknown keys: %s" % ", ".join(sorted(bibliography.missing)), file=sys.stderr)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

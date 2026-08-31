#!/usr/bin/env python3
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "publications.json"
BIB_FILE = ROOT / "references.bib"
OUTPUT_FILE = ROOT / "publications.html"

KINDS = {"C", "P", "W"}

AWARDS = {
    "best": ("fa-trophy", "Best Paper award"),
    "honourable": ("fa-award", "Honourable Mention award"),
}

LINK_TYPES = {
    "pdf": ("pdf", "images/pdf_icon.png", "Open PDF in a new tab", "PDF"),
    "html": ("html", "images/html_icon.png", "Open HTML version in a new tab", "HTML"),
}

BIB_ENTRY_START = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,")


def fail(message):
    print("build_publications: " + message, file=sys.stderr)
    sys.exit(1)


def parse_bib(text):
    entries = {}
    for match in BIB_ENTRY_START.finditer(text):
        key = match.group(2)
        if key in entries:
            fail("duplicate BibTeX key '{}' in {}".format(key, BIB_FILE.name))
        start = text.index("{", match.start())
        depth = 0
        end = None
        for index in range(start, len(text)):
            character = text[index]
            if character == "{":
                depth += 1
            elif character == "}":
                depth -= 1
                if depth == 0:
                    end = index
                    break
        if end is None:
            fail("unterminated BibTeX entry '{}' in {}".format(key, BIB_FILE.name))
        entries[key] = text[match.start():end + 1].strip()
    return entries


def assign_ids(publications):
    counters = {}
    for publication in reversed(publications):
        kind = publication["kind"]
        counters[kind] = counters.get(kind, 0) + 1
        publication["id"] = "{}{}".format(kind, counters[kind])


def validate(publications, bib_entries, author):
    seen_slugs = set()
    seen_keys = set()

    for publication in publications:
        slug = publication.get("slug")
        if not slug:
            fail("a publication is missing 'slug'")
        if slug in seen_slugs:
            fail("duplicate slug '{}'".format(slug))
        seen_slugs.add(slug)

        for field in ("bibkey", "kind", "title", "authors", "venue", "year", "url"):
            if not publication.get(field):
                fail("'{}' is missing '{}'".format(slug, field))

        if publication["kind"] not in KINDS:
            fail("'{}' has unknown kind '{}', expected one of {}".format(
                slug, publication["kind"], ", ".join(sorted(KINDS))))

        award = publication.get("award")
        if award is not None and award not in AWARDS:
            fail("'{}' has unknown award '{}', expected one of {}".format(
                slug, award, ", ".join(sorted(AWARDS))))

        key = publication["bibkey"]
        if key in seen_keys:
            fail("bibkey '{}' is used by more than one publication".format(key))
        seen_keys.add(key)
        if key not in bib_entries:
            fail("'{}' references bibkey '{}', which is not in {}".format(
                slug, key, BIB_FILE.name))

        if author not in publication["authors"]:
            fail("'{}' does not list '{}' in its authors".format(slug, author))

        for link in publication.get("links", []):
            if link not in LINK_TYPES:
                fail("'{}' has unknown link type '{}', expected one of {}".format(
                    slug, link, ", ".join(sorted(LINK_TYPES))))
            if not (ROOT / link_path(slug, link)).is_file():
                fail("'{}' links to {}, which does not exist".format(
                    slug, link_path(slug, link)))

    unused = sorted(set(bib_entries) - seen_keys)
    if unused:
        print("build_publications: warning: unused BibTeX keys: {}".format(
            ", ".join(unused)), file=sys.stderr)


def link_path(slug, link):
    extension = LINK_TYPES[link][0]
    return "files/{}/{}.{}".format(slug, slug, extension)


def render_authors(authors, author):
    parts = []
    for name in authors:
        escaped = html.escape(name, quote=False)
        parts.append("<b>{}</b>".format(escaped) if name == author else escaped)
    return ", ".join(parts) + "."


def render_award(award):
    if award is None:
        return '                <div class="left-award"></div>'
    icon, label = AWARDS[award]
    return (
        '                <div class="left-award">\n'
        '                    <i class="fas {}" role="img" aria-label="{}"></i>\n'
        '                </div>'
    ).format(icon, label)


def render_links(slug, links):
    rendered = []
    for link in links:
        _, icon, label, text = LINK_TYPES[link]
        rendered.append((
            '                        <a href="./{}" target="_blank"\n'
            '                            aria-label="{}"><img alt="" src="{}"\n'
            '                                style="height: 1.5em" /> {}</a>'
        ).format(link_path(slug, link), label, icon, text))
    return "\n".join(rendered)


def render_publication(publication, bib_entries, author):
    bibtex = bib_entries[publication["bibkey"]].replace("</script", "<\\/script")
    return PUBLICATION_TEMPLATE \
        .replace("{{AWARD}}", render_award(publication.get("award"))) \
        .replace("{{AUTHORS}}", render_authors(publication["authors"], author)) \
        .replace("{{URL}}", html.escape(publication["url"], quote=True)) \
        .replace("{{TITLE}}", html.escape(publication["title"], quote=False)) \
        .replace("{{VENUE}}", html.escape(publication["venue"], quote=False)) \
        .replace("{{YEAR}}", str(publication["year"])) \
        .replace("{{LINKS}}", render_links(publication["slug"], publication.get("links", []))) \
        .replace("{{ID}}", publication["id"]) \
        .replace("{{BIBTEX}}", bibtex)


PUBLICATION_TEMPLATE = """\
            <div class="publication">
{{AWARD}}
                <div class="left">
                    {{AUTHORS}}
                    <a href="{{URL}}" target="_blank">{{TITLE}}<span class="visually-hidden">
                            (opens in a new tab)</span></a>
                    <i>in</i> {{VENUE}}, {{YEAR}}.
                    <p class="paper-links">
{{LINKS}}
                    </p>
                </div>
                <div class="right">
                    <span class="pub-id">{{ID}}</span>
                    <button class="button" aria-label="Cite {{ID}} - copy BibTeX to clipboard"
                        onclick="copy_citation(this)">
                        Cite
                    </button>
                    <script type="application/x-bibtex">
{{BIBTEX}}
</script>
                </div>
            </div>
            <hr>"""


PAGE_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="This is my person website">
    <meta name="author" content="Alexandre Nevsky">
    <link rel="icon" type="image/x-icon" href="./images/favicon.ico">
    <title>Publications - Alexandre Nevsky</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link
        href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible+Next:ital,wght@0,200..800;1,200..800&amp;display=swap"
        rel="stylesheet" data-styling>
    <link href="css/bootstrap.css" rel="stylesheet" data-styling>
    <link href="css/style.css" rel="stylesheet" data-styling>
    <link href="css/plain.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.3/css/all.min.css"
        integrity="sha512-iBBXm8fW90+nuLcSKlbmrPcLa0OT92xO1BIsZ+ywDWZCvqsWgccV3gFoRBv0z+8dLJgyAHIhR35VZc2oM/gI1w=="
        crossorigin="anonymous" referrerpolicy="no-referrer" />
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/jpswalsh/academicons@1/css/academicons.min.css">
    <script src="js/site.js"></script>
</head>

<body style="padding-left: calc(100vw - 100%);">
    <a class="skip-link" href="#main">Skip to main content</a>
    <nav class="navbar navbar-fixed-top navbar-inverse" role="navigation" style="padding-left: calc(100vw - 100%);">
        <div class="container">
            <ul class="nav navbar-nav">
                <li><a class="navbar-brand" href="./index.html">Home</a></li>
                <li><a class="nav_lesser" href="./publications.html" aria-current="page">Publications</a></li>
                <li><a class="nav_lesser" href="./cv.html">CV</a></li>
                <li><a class="nav_lesser" href="./other.html">Other</a></li>
            </ul>
            <div id="site-controls"></div>
        </div>
    </nav>

    <main class="container" id="main" tabindex="-1">
        <div class="row">
            <div class="col-lg-12">
                <h1 class="page-header">Publications</h1>
                <div style="font-size: 1.5em;">
                    <div style="padding-bottom: 0.75em;">
                        <b style="font-size: 1.2em;">C</b> for conference papers, <b style="font-size: 1.2em;">P</b> for
                        posters, and <b style="font-size: 1.2em;">W</b> for workshops.<br>
                    </div>
                    <div>
                        <i class="fas fa-trophy" role="img" aria-label="Trophy icon"></i> for Best Paper
                        and <i class="fas fa-award" role="img" aria-label="Award medal icon"></i> for Honourable
                        Mention.
                    </div>
                </div>
            </div>
            <hr>
        </div>

        <!-- PAPERS BELOW - generated by build_publications.py, do not edit by hand -->
        <div class="row">
{{PUBLICATIONS}}
        </div>
    </main>

    <script>
        function copy_citation(e) {
            const source = e.parentElement.querySelector('script[type="application/x-bibtex"]');
            navigator.clipboard.writeText(source.textContent.trim());
            e.className = "buttonClicked";
            setTimeout(() => {
                e.className = "button"
            }, 1000);
        }
    </script>
</body>

</html>
"""


def main():
    for path in (DATA_FILE, BIB_FILE):
        if not path.is_file():
            fail("{} not found".format(path.name))

    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        fail("{} is not valid JSON: {}".format(DATA_FILE.name, error))

    author = data.get("author")
    if not author:
        fail("{} is missing the top-level 'author' field".format(DATA_FILE.name))

    publications = data.get("publications")
    if not publications:
        fail("{} contains no publications".format(DATA_FILE.name))

    bib_entries = parse_bib(BIB_FILE.read_text(encoding="utf-8"))
    assign_ids(publications)
    validate(publications, bib_entries, author)

    rendered = "\n".join(
        render_publication(publication, bib_entries, author)
        for publication in publications
    )
    OUTPUT_FILE.write_text(
        PAGE_TEMPLATE.replace("{{PUBLICATIONS}}", rendered), encoding="utf-8")

    print("build_publications: wrote {} ({} publications)".format(
        OUTPUT_FILE.name, len(publications)))


if __name__ == "__main__":
    main()
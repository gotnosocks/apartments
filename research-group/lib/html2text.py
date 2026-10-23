"""Convert HTML on stdin to plain text, or DuckDuckGo result HTML to a result list (--ddg)."""

import html
import re
import sys
import urllib.parse
from html.parser import HTMLParser


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        if tag in ("p", "br", "div", "li", "h1", "h2", "h3", "h4", "tr", "title"):
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


src = sys.stdin.read()
if sys.argv[1:] == ["--ddg"]:
    for href, title in re.findall(
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', src, re.S
    ):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(html.unescape(href)).query)
        url = q.get("uddg", [html.unescape(href)])[0]
        print(re.sub(r"<[^>]+>", "", html.unescape(title)).strip(), "\n  ", url)
else:
    p = Text()
    p.feed(src)
    print(re.sub(r"\n\s*\n+", "\n\n", "".join(p.out)).strip())

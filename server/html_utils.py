import bleach
import re
from html.parser import HTMLParser
from difflib import SequenceMatcher
import urllib
from urllib.parse import urlparse
import os

from .errors import *


self_closing = ["br", "img"]
header_tags = ["h{}".format(x) for x in range(2, 7)]
whitespace = " \t\n\xa0"
allowed_tags = [
    "p",
    "div",
    "br",
    "b",
    "strong",
    "i",
    "em",
    "li",
    "ol",
    "ul",
    "a",
    "img",
]
allowed_attrs = {"a": ["href", "title"], "img": ["src"]}
img_exts = [".png", ".jpg", ".jpeg", ".gif"]


def name_to_title(name):
    return name.replace(" ", "_").replace("/", "|")


def title_to_name(title):
    return title.replace("_", " ").replace("|", "/")


def get_thread_title(href):
    match = re.fullmatch("^(http://|https://)?thread.wiki/page/([^/]+)(/)?$", href)
    if match is None:
        return None
    return match.group(2)


def linkify(html):
    links = set()

    def clean_link(attrs, new=False):
        if (None, "href") not in attrs:
            return None
        href = attrs[(None, "href")]
        thread_title = get_thread_title(href)
        if thread_title is None:
            _fnm, ext = os.path.splitext(urlparse(href).path)
            if ext.lower() in img_exts:
                print("making image")
                attrs["_text"] = sanitize_html("<img src='{}'>".format(href))
            else:
                attrs["_text"] = sanitize_text(href)
        else:
            attrs["_text"] = sanitize_text(
                urllib.parse.unquote(title_to_name(thread_title))
            )
            links.add(thread_title)
        return attrs

    linker = bleach.Linker(
        callbacks=[clean_link], url_re=bleach.linkifier.build_url_re(tlds=["[a-z]+"])
    )
    return links, linker.linkify(html)


def linkify_page(sections, summary):
    links, summary = linkify(summary)
    for section in sections:
        section_links, section.body = linkify(section.body)
        links = links.union(section_links)
    return links, sections, summary


def sanitize_html(html):
    return bleach.clean(
        str(html), tags=allowed_tags + header_tags, attributes=allowed_attrs, strip=True
    )


def sanitize_paragraph(html):
    return bleach.clean(
        str(html), tags=allowed_tags, attributes=allowed_attrs, strip=True
    )


def sanitize_text(text):
    if text == "":
        raise EmptyString()
    return bleach.clean(str(text), tags=[], strip=True)


def splitstrip(s):
    lstripped = s.lstrip(whitespace)
    rstripped = s.rstrip(whitespace)
    lwhitespace = len(s) - len(lstripped)
    rwhitespace = len(rstripped)
    return s[:lwhitespace], s[lwhitespace:rwhitespace], s[rwhitespace:]


def is_word(s):
    return len(s.strip(whitespace)) > 0


def split_words(data):
    words = []
    start = 0
    for i in range(len(data)):
        if i == len(data) - 1:
            words.append(data[start:])
            break
        if (
            data[i] in whitespace
            and data[i + 1] not in whitespace
            and is_word(data[start : i + 1])
        ):
            words.append(data[start : i + 1])
            start = i + 1
    return words


def immutify(data):
    if isinstance(data, tuple) or isinstance(data, list):
        return tuple(immutify(x) for x in data)
    else:
        return data


class Token:
    def __init__(self, identity):
        self.identity = immutify(identity)

    def mark_dirty(self):
        self.identity = (self.identity, True)

    def __eq__(self, other):
        return self.identity == other.identity

    def __hash__(self):
        return hash(self.identity)


class DataToken(Token):
    def __init__(self, data, context):
        super().__init__((data.strip(whitespace), context))
        self.data = data
        self.context = context

    def __repr__(self):
        return "{}({})".format(repr(self.data), ",".join(t for t, a in self.context))


class TagToken(Token):
    def __init__(self, tag, context, attrs):
        super().__init__((tag, context, attrs))
        self.tag = tag
        self.context = context
        self.attrs = attrs

    def __repr__(self):
        return "<{}>({})".format(self.tag, ",".join(t for t, a in self.context))


class HTMLSequencer(HTMLParser):
    def __init__(self):
        super().__init__()

        self.context = []
        self.sequence = []

        self.just_closed = None

    def handle_starttag(self, tag, attrs):
        if tag in self_closing:
            self.sequence.append(TagToken(tag, self.context.copy(), attrs))
        else:
            if (tag, attrs) == self.just_closed:
                self.sequence.append(DataToken("", self.context.copy()))
            else:
                self.just_closed = None
            self.context.append((tag, attrs))

    def handle_endtag(self, end_tag):
        if not self.context:
            print("Warning: mismatched tag `{}`".format(end_tag))
        start_tag, attrs = self.context.pop()
        if start_tag != end_tag:
            print("Warning: mismatched tag `{}`".format(end_tag))
        self.just_closed = (start_tag, attrs)

    def handle_data(self, data):
        words = split_words(data)
        for word in words:
            self.sequence.append(DataToken(word, self.context.copy()))


def list_difference(xs, ys):
    i = 0
    while True:
        if i in [len(xs), len(ys)] or xs[i] != ys[i]:
            break
        i += 1
    return xs[:i], xs[i:], ys[i:]


def open_tag(tag, attrs):
    if not attrs:
        return "<{}>".format(tag)
    return "<{} {}>".format(
        tag, " ".join("{}={}".format(prop, repr(val)) for prop, val in attrs)
    )


def close_tag(tag):
    return "</{}>".format(tag)


def generate_html(sequence):
    html = []
    context = []
    for token in sequence:
        shared, to_close, to_open = list_difference(context, token.context)
        for tag, attrs in reversed(to_close):
            html.append(close_tag(tag))
        for tag, attrs in to_open:
            html.append(open_tag(tag, attrs))
        if isinstance(token, DataToken):
            html.append(token.data)
        elif isinstance(token, TagToken):
            html.append(open_tag(token.tag, token.attrs))
        else:
            raise Exception("Oops, what happened here?")
        context = token.context
    for tag, attrs in reversed(context):
        html.append(close_tag(tag))
    return "".join(html).strip(" \n")


def startswith(l, prefix):
    return l[: len(prefix)] == prefix


def insert_tags(sequence, tag, predicate):
    prefix = None
    for add_tag, token in zip(predicate, sequence):
        if add_tag:
            if prefix is None or not startswith(token.context, prefix):
                prefix = token.context
            token.context.insert(len(prefix), tag)
        else:
            prefix = None


def get_sequence(data):
    parser = HTMLSequencer()
    parser.feed(data)
    return parser.sequence


def add_diff_to_context(matcher, sequence_a, sequence_b):
    merged_sequence = []
    diff = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            merged_sequence += sequence_b[j1:j2]
            diff += ["equal"] * (j2 - j1)
        if tag == "replace" or tag == "delete":
            merged_sequence += sequence_a[i1:i2]
            diff += ["del"] * (i2 - i1)
        if tag == "replace" or tag == "insert":
            merged_sequence += sequence_b[j1:j2]
            diff += ["ins"] * (j2 - j1)
    insert_tags(merged_sequence, ("del", []), (x == "del" for x in diff))
    insert_tags(merged_sequence, ("ins", []), (x == "ins" for x in diff))
    return merged_sequence


def wrap_brackets(tokens):
    for token in tokens:
        if isinstance(token, DataToken) and is_word(token.data):
            l, s, r = splitstrip(token.data)
            token.data = l + "[" + s + r
            break
    for token in reversed(tokens):
        if isinstance(token, DataToken) and is_word(token.data):
            l, s, r = splitstrip(token.data)
            token.data = l + s + "]" + r
            break
    return tokens


def empty_brackets(token):
    return DataToken("[]", token.context)


def contains_word(tokens):
    for token in tokens:
        if isinstance(token, DataToken) and is_word(token.data):
            return True
    return False


def stretched_opcodes(matcher, sequence_a, sequence_b, n=3, depth=0, maxdepth=3):
    marked_dirty = False
    opcodes = matcher.get_opcodes()
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal" and (j2 - j1) < n:
            for token in sequence_b[j1:j2]:
                marked_dirty = True
                token.mark_dirty()
    if not marked_dirty:
        return opcodes
    stretched_matcher = SequenceMatcher(
        isjunk=None, a=sequence_a, b=sequence_b, autojunk=False
    )
    if depth >= maxdepth:
        return stretched_matcher.get_opcodes()
    return stretched_opcodes(
        stretched_matcher,
        sequence_a,
        sequence_b,
        n=n,
        depth=depth + 1,
        maxdepth=maxdepth,
    )


def add_concise_diff_to_context(matcher, sequence_a, sequence_b):
    merged_sequence = []
    diff = []
    for tag, i1, i2, j1, j2 in stretched_opcodes(matcher, sequence_a, sequence_b):
        if tag == "equal":
            merged_sequence += sequence_b[j1:j2]
            diff += ["equal"] * (j2 - j1)
        if tag == "delete":
            if contains_word(sequence_a[i1:i2]):
                merged_sequence += [empty_brackets(sequence_a[i1])]
                diff += ["del"]
        if tag == "replace" or tag == "insert":
            merged_sequence += wrap_brackets(sequence_b[j1:j2])
            diff += ["ins"] * (j2 - j1)
    insert_tags(merged_sequence, ("del", []), (x == "del" for x in diff))
    insert_tags(merged_sequence, ("ins", []), (x == "ins" for x in diff))
    return merged_sequence


def markup_changes(data_a, data_b, concise=False):
    sequence_a = get_sequence(data_a)
    sequence_b = get_sequence(data_b)
    matcher = SequenceMatcher(isjunk=None, a=sequence_a, b=sequence_b, autojunk=False)
    diff_fn = add_concise_diff_to_context if concise else add_diff_to_context
    merged_sequence = diff_fn(matcher, sequence_a, sequence_b)
    return generate_html(merged_sequence)

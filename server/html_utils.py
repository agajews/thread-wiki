import bleach
from html.parser import HTMLParser
from difflib import SequenceMatcher
import itertools


self_closing = ["br"]
whitespace = [" ", "\t", "\n"]
allowed_tags = [
    "p",
    "div",
    "span",
    "br",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "b",
    "strong",
    "i",
    "em",
    "li",
    "ol",
    "ul",
    "a",
]


def sanitize_html(html):
    return bleach.clean(html, tags=allowed_tags)


def split_words(data):
    words = []
    start = 0
    for i in range(len(data)):
        if i == len(data) - 1:
            words.append(data[start:])
            break
        if data[i] in whitespace and data[i + 1] not in whitespace:
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

    def __eq__(self, other):
        return self.identity == other.identity

    def __hash__(self):
        return hash(self.identity)


class DataToken(Token):
    def __init__(self, data, context):
        super().__init__((data, context))
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
    return "".join(html)


def startswith(l, prefix):
    return l[: len(prefix)] == prefix


def insert_tags(sequence, tag, predicate):
    prefix = None
    context = []
    for add_tag, token in zip(predicate, sequence):
        if add_tag:
            if prefix is None or not startswith(token.context, prefix):
                shared, to_close, to_open = list_difference(context, token.context)
                prefix = shared
            token.context.insert(len(prefix), tag)
        else:
            prefix = None
        context = token.context


def get_sequence(data):
    parser = HTMLSequencer()
    parser.feed(data)
    return parser.sequence


def add_diff_to_context(opcodes, sequence_a, sequence_b):
    merged_sequence = []
    diff = []
    for tag, i1, i2, j1, j2 in opcodes:
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


def isjunk(token):
    if isinstance(token, DataToken) and all(c in whitespace for c in token.data):
        return True
    return False


def markup_changes(data_a, data_b):
    sequence_a = get_sequence(data_a)
    sequence_b = get_sequence(data_b)
    matcher = SequenceMatcher(isjunk=isjunk, a=sequence_a, b=sequence_b, autojunk=False)
    merged_sequence = add_diff_to_context(matcher.get_opcodes(), sequence_a, sequence_b)
    return generate_html(merged_sequence)


def markup_change_blocks(data_a, data_b):
    sequence_a = get_sequence(data_a)
    sequence_b = get_sequence(data_b)
    matcher = SequenceMatcher(isjunk=isjunk, a=sequence_a, b=sequence_b, autojunk=False)
    blocks = []
    for opcodes in matcher.get_grouped_opcodes(n=5):
        merged_sequence = add_diff_to_context(opcodes, sequence_a, sequence_b)
        blocks.append(generate_html(merged_sequence))
    return blocks


def is_header(token):
    return any("h{}".format(x) in token.context for x in range(2, 7))


def get_header_level(group):
    for x in range(2, 7):
        if "h{}".format(x) in group[0].context:
            return x
    return None


def extract_text(tokens):
    text = ""
    for token in tokens:
        if isinstance(token, DataToken):
            text += token.data
    return text


def separate_sections(data):
    sequence = get_sequence(data)
    keys, groups = itertools.groupby(sequence, key=is_header)
    i = 0
    if keys[0] == False:
        summary = generate_html(groups[0])
        i += 1
    else:
        summary = ""
    sections = []
    while i < len(groups):
        sections.append(
            {
                "header": extract_text(groups[i]),
                "body": generate_html(groups[i + 1]) if i + 1 < len(groups) else "",
                "level": get_header_level(groups[i]),
            }
        )
        i += 1
    return summary, sections


class Section(Token):
    def __init__(self, section):
        self.header = section["header"]
        self.body = section["body"]
        self.level = section["level"]
        super().__init__((self.header, self.level))

    def to_dict(self):
        return {"header": section.header, "body": section.body, "level": section.level}


def diff_sections(sections_a, sections_b):
    sequence_a = [Section(section) for section in sections_a]
    sequence_b = [Section(section) for section in sections_b]
    matcher = SequenceMatcher(isjunk=isjunk, a=sequence_a, b=sequence_b, autojunk=False)
    merged_sequence = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for section_a, section_b in zip(sequence_a[i1:i2], sequence_b[j1:j2]):
                section_dict = section.to_dict()
                if section_a.body != section_b.body:
                    section["diff"] = markup_changes(section_a.body, section_b.body)
                merged_sequence.append(section_dict)
        if tag == "replace" or tag == "delete":
            for section in sequence_a[i1:i2]:
                section_dict = section.to_dict()
                section_dict["deleted"] = True
                merged_sequence.append(section_dict)
        if tag == "replace" or tag == "insert":
            for section in sequence_b[j1:j2]:
                section_dict = section.to_dict()
                section_dict["inserted"] = True
                merged_sequence.append(section_dict)
    return merged_sequence

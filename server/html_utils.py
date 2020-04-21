import bleach
from html.parser import HTMLParser
from difflib import SequenceMatcher


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
    for opcodes in matcher.get_grouped_opcodes(n=3):
        merged_sequence = add_diff_to_context(opcodes, sequence_a, sequence_b)
        blocks.append(generate_html(merged_sequence))
    return blocks

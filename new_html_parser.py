from html.parser import HTMLParser
from difflib import SequenceMatcher


self_closing = ["br"]
whitespace = [" ", "\t", "\n"]


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
        self.inserted = False
        self.deleted = False

    def __repr__(self):
        ins = ""
        if self.inserted:
            ins = "{ins}"
        elif self.deleted:
            ins = "{del}"
        return "{}({}){}".format(
            repr(self.data), ",".join(t for t, a in self.context), ins
        )


class TagToken(Token):
    def __init__(self, tag, context, attrs):
        super().__init__((tag, context, attrs))
        self.tag = tag
        self.context = context
        self.attrs = attrs
        self.inserted = False
        self.deleted = False

    def __repr__(self):
        ins = ""
        if self.inserted:
            ins = "{ins}"
        elif self.deleted:
            ins = "{del}"
        return "<{}>({}){}".format(self.tag, ",".join(t for t, a in self.context), ins)


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
    return xs[i:], ys[i:]


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
        to_close, to_open = list_difference(context, token.context)
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
    if prefix is None:
        return False
    return l[: len(prefix)] == prefix


def insert_diff_tags(sequence):
    insert_prefix = None
    delete_prefix = None
    for token in sequence:
        if token.inserted:
            if startswith(token.context, insert_prefix):
                token.context.insert(len(insert_prefix), [("ins", [])])
            else:
                insert_prefix = token.context
                token.context.append(("ins", []))
        else:
            insert_prefix = None

        if token.deleted:
            if startswith(token.context, delete_prefix):
                token.context.insert(len(delete_prefix), [("del", [])])
            else:
                delete_prefix = token.context
                token.context.append(("del", []))
        else:
            delete_prefix = None


def get_sequence(data):
    parser = HTMLSequencer()
    parser.feed(data)
    return parser.sequence


def markup_changes(data_a, data_b):
    sequence_a = get_sequence(data_a)
    sequence_b = get_sequence(data_b)
    matcher = SequenceMatcher(isjunk=None, a=sequence_a, b=sequence_b, autojunk=False)
    merged_sequence = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            merged_sequence += sequence_b[j1:j2]
        if tag == "replace" or tag == "delete":
            for token in sequence_a[i1:i2]:
                token.deleted = True
                merged_sequence.append(token)
        if tag == "replace" or tag == "insert":
            for token in sequence_b[j1:j2]:
                token.inserted = True
                merged_sequence.append(token)
    # print("\n".join(repr(t) for t in merged_sequence))
    # print("=========")
    insert_diff_tags(merged_sequence)
    return generate_html(merged_sequence)


data_a = """
<h1>This is just a header</h1>
<div>This is a body paragraph that goes along with it.</div>

<h2>This is another header</h2>
<div>This body paragraph has a bulleted list:
    <ul>
        <li>yo</li>
        <li>yoyo</li>
        <li>This one is nested:<ul>
            <li>yo</li>
            <li>yoyo</li>
        </ul></li>
    </ul>
    This is the end of the paragraph.
</div>
"""

data_b = """
<h1>This is a header</h1>
<div>This is a related paragraph that goes along with it.</div>

<h2>This is <strong>another</strong> header</h2>
<div>This is an entirely new <em>body</em> paragraph.</div>
<div>This body paragraph has a bulleted list:
    <ul>
        <li>yo</li>
        <li>hyohyo</li>
        <li>This one is nested:<ul><ul>
            <li>yo</li>
            <li>yoyo</li>
        </ul></ul></li>
    </ul>
    This is the end of the paragraph.
</div>
"""


print(markup_changes(data_a, data_b))


# print(split_words("hello world!"))
# print(split_words("hello world! "))
# parser = HTMLSequencer()
# parser.feed(
#     "<h1>This is <em>a</em> header</h1>\n\n"
#     "<div><p>This is the <strong>beginning</strong> of <br><br>my paragraph.</p></div>\n\n"
#     "<h2><strong><em>This is a <a href='https://google.com'>sub-header</a></em></strong></h2>\n"
#     "<div><p>This is the <em>middle</em> of my document.</p></div>"
#     "<div>This is a bulleted list: <ul><li>yo</li><li>yolo</li></ul></div>"
# )
# print("\n".join(repr(t) for t in parser.sequence))
# print("\n\n===HTML===")
# print(generate_html(parser.sequence))

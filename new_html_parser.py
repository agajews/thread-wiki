from html.parser import HTMLParser


self_closing = ["br"]


def split_words(data):
    words = []
    word = ""
    for char in data:
        word += char
        if char in [" ", "\t", "\n"]:
            words.append(word)
            word = ""
    if word:
        words.append(word)
    return words


class DataToken:
    def __init__(self, data, context):
        self.data = data
        self.context = context

    def __repr__(self):
        return "{}({})".format(repr(self.data), ",".join(t for t, a in self.context))


class TagToken:
    def __init__(self, tag, context, attrs):
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

    def handle_starttag(self, tag, attrs):
        if tag in self_closing:
            self.sequence.append(TagToken(tag, self.context.copy(), attrs))
        else:
            self.context.append((tag, attrs))

    def handle_endtag(self, end_tag):
        if not self.context:
            print("Warning: mismatched tag `{}`".format(end_tag))
        start_tag, attrs = self.context.pop()
        if start_tag != end_tag:
            print("Warning: mismatched tag `{}`".format(end_tag))

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


print(split_words("hello world!"))
print(split_words("hello world! "))
parser = HTMLSequencer()
parser.feed(
    "<h1>This is <em>a</em> header</h1>\n\n"
    "<div><p>This is the <strong>beginning</strong> of <br><br>my paragraph.</p></div>\n\n"
    "<h2><strong><em>This is a <a href='https://google.com'>sub-header</a></em></strong></h2>\n"
    "<div><p>This is the <em>middle</em> of my document.</p></div>"
)
print("\n".join(repr(t) for t in parser.sequence))
print("\n\n===HTML===")
print(generate_html(parser.sequence))

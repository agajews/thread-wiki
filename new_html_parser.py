from html.parser import HTMLParser


self_closing = ["br"]


class DataToken:
    def __init__(self, data, context):
        self.data = data
        self.context = context

    def __repr__(self):
        return "{}({})".format(repr(self.data), ",".join(self.context))


class TagToken:
    def __init__(self, tag, context):
        self.tag = tag
        self.context = context

    def __repr__(self):
        return "<{}>({})".format(self.tag, ",".join(self.context))


class MyHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()

        self.context = []
        self.sequence = []

    def handle_starttag(self, tag, attrs):
        if tag in self_closing:
            self.sequence.append(TagToken(tag, self.context.copy()))
        else:
            self.context.append(tag)

    def handle_endtag(self, end_tag):
        if not self.context:
            print("Warning: mismatched tag `{}`".format(end_tag))
        start_tag = self.context.pop()
        if start_tag != end_tag:
            print("Warning: mismatched tag `{}`".format(end_tag))

    def handle_data(self, data):
        self.sequence.append(DataToken(data, self.context.copy()))


def list_difference(xs, ys):
    i = 0
    while True:
        if i in [len(xs), len(ys)] or xs[i] != ys[i]:
            break
        i += 1
    return xs[i:], ys[i:]


def generate_html(sequence):
    html = []
    context = []
    for token in sequence:
        to_close, to_open = list_difference(context, token.context)
        for tag in reversed(to_close):
            html.append("</{}>".format(tag))
        for tag in to_open:
            html.append("<{}>".format(tag))
        if isinstance(token, DataToken):
            html.append(token.data)
        elif isinstance(token, TagToken):
            html.append("<{}>".format(token.tag))
        else:
            raise Exception("Oops, what happened here?")
        context = token.context
    for tag in reversed(context):
        html.append("</{}>".format(tag))
    return "".join(html)


parser = MyHTMLParser()
parser.feed(
    "<h1>This is <em>a</em> header</h1>\n\n"
    "<div><p>This is the <strong>beginning</strong> of my paragraph.</p></div>\n\n"
    "<h2><strong><em>This is a sub-header</em></strong></h2>\n"
    "<div>This is the <em>middle</em> of my document.</div>"
)
print("\n".join(repr(t) for t in parser.sequence))
print("\n\n===HTML===")
print(generate_html(parser.sequence))

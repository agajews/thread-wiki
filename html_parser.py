from html.parser import HTMLParser


class Token:
    def __init__(
        self, tokentype, data=None, bolded=False, italicized=False, header=None
    ):
        self.tokentype = tokentype
        self.data = data
        self.bolded = bolded
        self.italicized = italicized
        self.header = header

    def __repr__(self):
        if self.tokentype == "br":
            return "(br)"
        elif self.tokentype == "data":
            attributes = []
            if self.bolded:
                attributes.append("strong")
            if self.italicized:
                attributes.append("em")
            if self.header is not None:
                attributes.append("h{}".format(self.header))
            return "{}({})".format(repr(self.data), ",".join(attributes))


class Tag:
    def __init__(self, name, skipping=False):
        self.name = name
        self.skipping = skipping


class MyHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()

        self.tags = []
        self.sequence = []

        self.bolded = False
        self.italicized = False
        self.header = None

    def handle_starttag(self, tagname, attrs):
        tag = Tag(tagname)
        if tagname in ["b", "strong"] and not self.bolded:
            self.bolded = True
        elif tagname in ["i", "em"] and not self.italicized:
            self.italicized = True
        elif tagname in ["p", "div"]:
            pass
        elif tagname in ["h1", "h2", "h3", "h4", "h5", "h6"] and self.header is None:
            self.header = int(tagname[1])
        else:
            tag.skipping = True
        self.tags.append(tag)

    def handle_endtag(self, tagname):
        if not self.tags:
            raise Exception("Malformed HTML")
        tag = self.tags.pop()
        if tag.name != tagname:
            print("Warning: mismatched tag `{}`".format(tagname))
        if tag.skipping:
            return
        if tag.name in ["b", "strong"]:
            self.bolded = False
        elif tag.name in ["i", "em"]:
            self.italicized = False
        elif tag.name in ["p", "div"]:
            self.sequence.append(
                Token(
                    "br",
                    bolded=self.bolded,
                    italicized=self.italicized,
                    header=self.header,
                )
            )
        elif tag.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            self.header = None
        else:
            raise Exception("Oops, what happened here?")

    def handle_data(self, data):
        self.sequence.append(
            Token(
                "data",
                data,
                bolded=self.bolded,
                italicized=self.italicized,
                header=self.header,
            )
        )


def generate_html(sequence):
    bolded = False
    italicized = False
    header = None

    html = []

    for token in sequence:
        # have to close and open in reverse order
        # bc we want our html to be well-formatted
        if not token.bolded and bolded:
            html.append("</strong>")
        if not token.italicized and italicized:
            html.append("</em>")
        if token.header != header and header is not None:
            html.append("</h{}>".format(header))
        if token.header != header and token.header is not None:
            html.append("<h{}>".format(token.header))
        if token.italicized and not italicized:
            html.append("<em>")
        if token.bolded and not bolded:
            html.append("<strong>")
        bolded = token.bolded
        italicized = token.italicized
        header = token.header

        if token.tokentype == "br":
            html.append("<br>")
        elif token.tokentype == "data":
            html.append(token.data)

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

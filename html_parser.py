from html.parser import HTMLParser


class Token:
    def __init__(
        self, tokentype, data=None, bolded=False, italicized=False, header=None
    ):
        self.tokentype = tokentype
        self.data = data
        self.bolded = bolded
        self.italicized = italicized
        self.header = None

    def __repr__(self):
        if self.tokentype == "br":
            return "(br)"
        elif self.tokentype == "data":
            return "{}({}{}{})".format(
                repr(self.data),
                "b" if self.bolded else "",
                "i" if self.italicized else "",
                "h{}".format(self.header) if self.header is not None else "",
            )


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
            self.sequence.append(Token("br"))
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


parser = MyHTMLParser()
parser.feed("<p>Parse <b>me</b>!</p>")
print(parser.sequence)

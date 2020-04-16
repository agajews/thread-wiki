import bleach


def sanitize_html(html):
    return bleach.clean(
        html,
        tags=[
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
        ],
    )

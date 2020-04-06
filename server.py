from flask import Flask, render_template, abort


app = Flask(__name__)


class UserPage:
    def __init__(self, name, summary, sections):
        self.name = name
        self.summary = summary
        self.sections = sections


class Section:
    def __init__(self, title, body):
        self.title = title
        self.body = body


users = {
    "allison": UserPage(
        "Allison Ghuman",
        "Allison is a person. Who lives here.",
        sections=[
            Section(
                "Early life", "Allison was born in texas but doesn't like it there."
            ),
            Section(
                "Rise to power",
                "When she was a young adult, she took over the world and became an uber rich.",
            ),
        ],
    )
}


@app.route("/")
def index():
    return render_template("index.html", users=users)


@app.route("/page/<name>")
def page(name):
    if name in users:
        return render_template("user-page.html", user=users[name])
    abort(404)

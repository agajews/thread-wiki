from flask import render_template, abort, request, jsonify, g, redirect
import re
from copy import deepcopy
from .app import app, db, timestamp, url_for
from .auth import verify_password, generate_auth_token
from .html_utils import sanitize_html, separate_sections
from .database import create_user_page, edit_user_page


@app.route("/")
def index():
    pages = db.pages.find(
        {}, {"titles": {"$slice": -1}, "versions.heading": {"$slice": -1}}
    )
    return render_template("index.html", pages=pages)


def find_page(title):
    page = db.pages.find_one(
        {"titles": title}, {"versions": {"$slice": -1}, "type": 1, "titles": 1}
    )
    return page


def is_valid_email(email):
    if re.match("^[a-zA-Z0-9.\\-_]+@([a-zA-Z0-9\\-_]+.)+edu$", email):
        return True
    return False


@app.route("/page/<title>/")
def page(title):
    print("Finding page {}".format(title))
    page = find_page(title)
    if page is not None and page["type"] == "user":
        if title != page["titles"][-1]:
            return redirect(url_for("page", title=page["titles"][-1]))
        return render_template(
            "user-page.html", version=page["versions"][-1], title=title
        )
    if is_valid_email(title):
        create_user_page(title)
        page = find_page(title)
        return render_template(
            "user-page.html", version=page["versions"][-1], title=title
        )

    abort(404)  # eventually, create new topic page


@app.route("/page/<title>/edit/")
def edit(title):
    page = find_page(title)
    if g.user is None:
        abort(401)
    if page is not None and page["type"] == "user":
        return render_template(
            "edit-user-page.html", version=page["versions"][-1], title=title
        )
    abort(404)


def get_param(key):
    data = request.get_json(silent=True)
    if data is None or key not in data:
        abort(400)
    return data[key]


def signal(response=None, redirect=None, html=None):
    return jsonify({"response": response, "redirect": redirect, "html": html})


def failedit(errorkey, errorid):
    editerrors = {
        "racecondition": "Lel, someone else submitted an edit while you were working on this one. Try merging your edits into that version instead (e.g. by opening edit page in a new tab).",
        "duplicatekey": "Lel, someone with the same name already has that nickname!",
        "emptyedit": "Lel, doesn't look like you changed anything.",
    }
    return signal(html={errorid: editerrors[errorkey]})


@app.route("/page/<title>/submitedit/", methods=["POST"])
def submitedit(title):
    page = db.pages.find_one(
        {"titles": title, "versions": {"$size": get_param("num")}},
        {"titles": 1, "type": 1, "versions": {"$slice": -1}, "owner": 1, "primary": 1},
    )
    if page is None:
        return failedit("racecondition", "editerror")

    summary, sections = separate_sections(sanitize_html(get_param("body")))
    content = {
        "sections": sections,
        "summary": summary,
        "heading": get_param("heading"),
        "nickname": get_param("nickname"),
    }
    update = edit_user_page(page, content)
    if "error" in update:
        return failedit(update["error"], "editerror")
    return signal(redirect=url_for("page", title=update["newtitle"]))


@app.route("/page/<title>/sectionedit/<int:idx>/", methods=["POST"])
def sectionedit(title, idx):
    page = db.pages.find_one(
        {"titles": title, "versions": {"$size": get_param("num")}},
        {"titles": 1, "type": 1, "versions": {"$slice": -1}, "owner": 1, "primary": 1},
    )
    errorid = "editerror-section-{}".format(idx)
    if page is None:
        return failedit("racecondition", errorid)

    content = deepcopy(page["versions"][-1]["content"])
    if idx >= len(content["sections"]):
        abort(400)
    content["sections"][idx]["body"] = sanitize_html(get_param("body"))
    update = edit_user_page(page, content)
    if "error" in update:
        if update["error"] == "emptyedit":
            return signal(response={"done": True})
        return failedit(update["error"], errorid)
    for section in update["primarydiff"]["sections"]:
        if section["idx"] == idx:
            updated_diff = section["diff"]
    return signal(
        response={"done": True, "increment": True},
        html={errorid: "", "section-diff-{}".format(idx): updated_diff},
    )


@app.route("/page/<title>/summaryedit/", methods=["POST"])
def summaryedit(title):
    page = db.pages.find_one(
        {"titles": title, "versions": {"$size": get_param("num")}},
        {"titles": 1, "type": 1, "versions": {"$slice": -1}, "owner": 1, "primary": 1},
    )
    if page is None:
        return failedit("racecondition", "summaryerror")

    content = deepcopy(page["versions"][-1]["content"])
    content["summary"] = sanitize_html(get_param("body"))
    update = edit_user_page(page, content)
    if "error" in update:
        if update["error"] == "emptyedit":
            return signal(response={"done": True})
        return failedit(update["error"], "summaryerror")
    return signal(
        response={"done": True, "increment": True},
        html={"summaryerror": "", "summary-diff": update["primarydiff"]["summary"]},
    )


@app.route("/page/<title>/version/<int:num>/")
def version(title, num):
    page = db.pages.find_one({"titles": title}, {"versions": {"$slice": [num - 1, 1]}})
    if page is not None and page["type"] == "user" and page["versions"]:
        return render_template(
            "user-page-version.html", version=page["versions"][0], title=title
        )
    abort(404)


@app.route("/page/<title>/history/")
def history(title):
    page = db.pages.find_one({"titles": title})
    if page is None:
        abort(404)
    if g.user is None:
        abort(401)
    return render_template(
        "user-page-history.html",
        currentversion=page["versions"][-1],
        oldversions=reversed(page["versions"][1:-1]),
        initialversion=page["versions"][0],
        title=title,
    )


@app.route("/authenticate/", methods=["POST"])
def authenticate():
    verified = verify_password(get_param("email"), get_param("password"))
    g.user = verified.get("user")
    g.reissue_token = True
    if g.user is None:
        return signal(html={"loginerror": verified["error"]})
    return signal(redirect=get_param("href"))


@app.route("/logout/", methods=["POST"])
def logout():
    g.user = None
    g.rerender = True
    return signal(redirect=get_param("href"))

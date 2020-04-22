from flask import (
    render_template,
    abort,
    request,
    jsonify,
    get_template_attribute,
    g,
    redirect,
    url_for,
)
import re
import random
from pymongo.errors import DuplicateKeyError
from .html_utils import sanitize_html, markup_changes, separate_sections, diff_sections
from .app import app, db, timestamp
from .auth import verify_password, generate_auth_token


def url_for_title(*args, **kwargs):
    return url_for(*args, **kwargs).replace("%40", "@")


@app.context_processor
def inject_url_for_title():
    return dict(url_for_title=url_for_title)


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


def generate_user_template(email):
    return "<p>The homo sapiens {0} is simply the best.</p><h2>Best Quotes</h2><p>Yoyoyo, it's my boy {0}</p><h2>Early life</h2><p>One day, our protagonist {0} was born. Later, they went to college.</p>".format(
        email
    )


def generate_nickname():
    return random.choice(
        [
            "Benevolent Dictator",
            "A Reasonable Person",
            "Mother Away From Home",
            "I ran out of ideas for nicknames",
            "The Best Chef This World Has Ever Seen",
            "Pure Instinct",
            "Fascinator",
            "Analyst",
        ]
    )


def build_user_title(heading, nickname):
    return (heading + "_" + nickname).replace(" ", "_")


def diff_versions(content_a, content_b):
    return {
        "sections": diff_sections(content_a["sections"], content_b["sections"]),
        "summary": markup_changes(content_a["summary"], content_b["summary"]),
        "summarychanged": content_a["summary"] != content_b["summary"],
        "headingchanged": content_a["heading"] != content_b["heading"],
        "nicknamechanged": content_a["nickname"] != content_b["nickname"],
    }


emptycontent = {"sections": [], "summary": "", "heading": "", "nickname": ""}


def create_user_page(title):
    nickname = generate_nickname()
    summary, sections = separate_sections(generate_user_template(title))
    content = {
        "sections": sections,
        "summary": summary,
        "heading": title,
        "nickname": nickname,
    }
    try:
        db.pages.insert_one(
            {
                "titles": [title, build_user_title(title, nickname)],
                "type": "user",
                "owner": title,
                "versions": [
                    {
                        "content": content,
                        "diff": diff_versions(emptycontent, content),
                        "editor": g.user["_id"],
                        "timestamp": timestamp(),
                        "num": 1,
                    }
                ],
            }
        )
    except DuplicateKeyError:
        pass
    page = find_page(title)
    return render_template("user-page.html", version=page["versions"][-1], title=title)


@app.route("/page/<title>/")
def page(title):
    page = find_page(title)
    if page is not None and page["type"] == "user":
        if title != page["titles"][-1]:
            return redirect(url_for_title("page", title=page["titles"][-1]))
        return render_template(
            "user-page.html", version=page["versions"][-1], title=title
        )
    if g.user is None:
        abort(404)
    if is_valid_email(title):
        return create_user_page(title)
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


@app.route("/page/<title>/submitedit/", methods=["POST"])
def submitedit(title):
    def racecondition():
        return jsonify(
            {
                "success": False,
                "html": {
                    "editerror": "Oops, someone else submitted an edit while you were working on this one. Try merging your edits into that version instead (e.g. by opening this edit page in a new tab)."
                },
            }
        )

    def duplicatekey():
        return jsonify(
            {
                "success": False,
                "html": {
                    "editerror": "Oops, someone with the same name already has that nickname!"
                },
            }
        )

    data = request.get_json(silent=True)
    if data is None:
        abort(400)
    body = data.get("body")
    heading = data.get("heading")
    nickname = data.get("nickname")
    num = data.get("num")
    if body is None or heading is None or nickname is None or num is None:
        abort(400)

    page = db.pages.find_one(
        {"titles": title, "versions": {"$size": num}},
        {"titles": 1, "type": 1, "versions": {"$slice": -1}},
    )
    oldversion = page["versions"][-1]
    if page is None:
        return racecondition()
    if not page["type"] == "user":
        abort(400)
    if g.user is None:
        abort(401)

    sanitized_body = sanitize_html(body)
    summary, sections = separate_sections(sanitized_body)
    newtitle = build_user_title(heading, nickname)
    content = {
        "sections": sections,
        "summary": summary,
        "heading": heading,
        "nickname": nickname,
    }
    try:
        update = db.pages.update_one(
            {"titles": title, "versions": {"$size": num}},
            {
                "$push": {
                    "versions": {
                        "content": content,
                        "diff": diff_versions(oldversion["content"], content),
                        "editor": g.user["_id"],
                        "timestamp": timestamp(),
                        "num": num + 1,
                    }
                },
                "$addToSet": {"titles": newtitle},
            },
        )
    except DuplicateKeyError:
        return duplicatekey()
    if update.modified_count == 0:
        return racecondition()
    return jsonify({"success": True, "redirect": url_for_title("page", title=newtitle)})


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
    data = request.get_json(silent=True)
    if data is None:
        abort(400)
    verified = verify_password(data.get("email"), data.get("password"))
    g.user = verified.get("user")
    g.reissue_token = True
    g.login_error = verified.get("error")
    g.rerender = True
    return jsonify(html={"loginmodule": render_template("modules/login.html")})


@app.route("/logout/", methods=["POST"])
def logout():
    g.user = None
    g.rerender = True
    return jsonify(html={"loginmodule": render_template("modules/login.html")})

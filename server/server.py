from flask import (
    render_template,
    abort,
    request,
    jsonify,
    get_template_attribute,
    g,
    redirect,
)
import re
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
    page = find_page(title)
    if page is not None and page["type"] == "user":
        if title != page["titles"][-1]:
            return redirect(url_for("page", title=page["titles"][-1]))
        return render_template(
            "user-page.html", version=page["versions"][-1], title=title
        )
    if g.user is None:
        abort(404)
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


def failedit(errorkey):
    errors = {
        "racecondition": "Lel, someone else submitted an edit while you were working on this one. Try merging your edits into that version instead (e.g. by opening this edit page in a new tab).",
        "duplicatekey": "Lel, someone with the same name already has that nickname!",
        "emptyedit": "Lel, doesn't look like you changed anything.",
    }

    return jsonify({"success": False, "html": {"editerror": errors[errorkey]}})


@app.route("/page/<title>/submitedit/", methods=["POST"])
def submitedit(title):
    if g.user is None:
        abort(401)

    page = db.pages.find_one(
        {"titles": title, "versions": {"$size": get_param("num")}},
        {"titles": 1, "type": 1, "versions": {"$slice": -1}, "owner": 1, "primary": 1},
    )
    if page is None:
        return failedit("racecondition")

    summary, sections = separate_sections(sanitize_html(get_param("body")))
    content = {
        "sections": sections,
        "summary": summary,
        "heading": get_param("heading"),
        "nickname": get_param("nickname"),
    }
    update = edit_user_page(page, content)
    if "error" in update:
        return failedit(update["error"])
    return jsonify(
        {"success": True, "redirect": url_for("page", title=update["newtitle"])}
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
    g.login_error = verified.get("error")
    g.rerender = True
    return jsonify(html={"loginmodule": render_template("modules/login.html")})


@app.route("/logout/", methods=["POST"])
def logout():
    g.user = None
    g.rerender = True
    return jsonify(html={"loginmodule": render_template("modules/login.html")})

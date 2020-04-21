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
from .html_utils import sanitize_html
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


# def find_userpage(username):
#     pages = db.userpages.find({"username": username}).sort("timestamp", -1).limit(1)
#     pages = list(pages)
#     if len(pages) == 0:
#         return None
#     return pages[0]


# def find_userpage_versions(username):
#     pages = db.userpages.find({"username": username}).sort("timestamp", -1)
#     if len(pages) == 0:
#         return None
#     return pages


def find_page(title):
    page = db.pages.find_one({"titles": title}, {"versions": {"$slice": -1}, "type": 1})
    return page


# def encode_title(title):
#     return title.replace("_", "%5F").replace(" ", "_")


# used for creating a new topic page from a url
# def decode_title(title):
#     return title.replace("_", " ")


def is_valid_email(email):
    if re.match("[a-zA-Z0-9.\\-_]+@([a-zA-Z0-9\\-_]+.)+edu", email):
        return True
    return False


def generate_user_template(email):
    return "<p>The homo sapiens {0} is simply the best.</p><h2>Best Quotes</h2><p>Yoyoyo, it's my boy {0}</p><h2>Early life</h2>One day, our protagonist {0} was born. Later, they went to college.</p>".format(
        email
    )


@app.route("/page/<title>/")
def page(title):
    page = find_page(title)
    if page is not None and page["type"] == "user":
        return render_template(
            "user-page.html", version=page["versions"][-1], title=title
        )
    if g.user is None:
        abort(404)
    if is_valid_email(title):
        db.pages.insert_one(
            {
                "titles": [title],
                "type": "user",
                "versions": [
                    {
                        "body": generate_user_template(title),
                        "heading": title,
                        "editor": g.user["_id"],
                        "timestamp": timestamp(),
                    }
                ],
            }
        )
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


# @app.route("/page/<title>/history/")
# def history(title):
#     versions = find_userpage_versions(title)
#     if versions is None:
#         abort(404)
#     if g.user is None:
#         abort(401)
#     return render_template("user-page-history.html", page=page)


@app.route("/page/<title>/submitedit/", methods=["POST"])
def submitedit(title):
    data = request.get_json(silent=True)
    if data is None:
        abort(400)
    body = data.get("body")
    heading = data.get("heading")
    if body is None or heading is None:
        abort(400)
    if g.user is None:
        abort(401)
    page = db.pages.find_one({"titles": title}, {"titles": 1})
    if page is None:
        abort(400)
    sanitized_body = sanitize_html(body)
    push = {
        "versions": {
            "body": sanitized_body,
            "heading": heading,
            "editor": g.user["_id"],
            "timestamp": timestamp(),
        }
    }
    newtitle = heading.replace(" ", "_")
    if newtitle not in page["titles"]:
        push["titles"] = newtitle
    update = db.pages.update_one({"titles": title}, {"$push": push})
    if update.modified_count > 0:
        return jsonify(
            {"success": True, "redirect": url_for_title("page", title=newtitle)}
        )
    return jsonify(
        {"success": False, "html": {"editerror": "Oops, something went wrong :("}}
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

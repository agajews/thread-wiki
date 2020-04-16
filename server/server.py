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
from .html_utils import sanitize_html
from .app import app, db, timestamp
from .auth import verify_password, generate_auth_token


@app.route("/")
def index():
    users = db.users.find()
    return render_template("index.html", users=users)


def find_userpage(username):
    pages = db.userpages.find({"username": username}).sort("timestamp", -1).limit(1)
    pages = list(pages)
    if len(pages) == 0:
        return None
    return pages[0]


@app.route("/page/<title>/")
def page(title):
    page = find_userpage(title)
    if page is None:
        abort(404)
    return render_template("user-page.html", page=page)


@app.route("/page/<title>/edit/")
def edit(title):
    page = find_userpage(title)
    if page is None:
        abort(404)
    if g.user is None:
        abort(401)
    return render_template("edit-user-page.html", page=page)


@app.route("/page/<title>/submitedit/", methods=["POST"])
def submitedit(title):
    data = request.get_json(silent=True)
    if data is None:
        abort(400)
    body = data.get("body")
    print(body)
    if body is None:
        abort(400)
    if g.user is None:
        abort(401)
    oldpage = find_userpage(title)
    if oldpage is None:
        abort(400)
    body = sanitize_html(body)
    db.userpages.insert(
        {
            "username": title,
            "name": oldpage["name"],
            "editor": g.user["username"],
            "body": body,
            "timestamp": timestamp(),
        }
    )
    return jsonify({"success": True})


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

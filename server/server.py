from flask import render_template, abort, request, jsonify, get_template_attribute, g
from .app import app, db
from .auth import verify_password, generate_auth_token


@app.route("/")
def index():
    userpages = db.userpages.find()
    return render_template("index.html", userpages=userpages)


@app.route("/page/<title>")
def page(title):
    page = db.userpages.find_one({"username": title})
    if page is None:
        abort(404)
    return render_template("user-page.html", page=page)


@app.route("/authenticate", methods=["POST"])
def authenticate():
    data = request.get_json()
    verified = verify_password(data.get("email"), data.get("password"))
    g.user = verified.get("user")
    g.login_error = verified.get("error")
    g.rerender = True
    res = jsonify(html={"loginmodule": render_template("modules/login.html")})
    g.reissue_token = True
    return res

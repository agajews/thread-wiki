from flask import render_template, abort, request, jsonify, get_template_attribute, g
from .app import app, db
from .auth import verify_password, generate_auth_token


@app.route("/")
def index():
    users = db.userpages.find()
    return render_template("index.html", users=users)


@app.route("/page/<title>")
def page(title):
    user = db.userpages.find_one({"username": title})
    if user is not None:
        return render_template("user-page.html", user=user)
    abort(404)


@app.route("/authenticate", methods=["POST"])
def authenticate():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")
    if email is None or password is None:
        return jsonify(
            html=render_template("modules/login.html", login_error="badrequest")
        )
    verified = verify_password(email, password)
    if "error" in verified:
        return jsonify(
            html=render_template("modules/login.html", login_error=verified["error"])
        )
    g.current_user = verified["user"]
    return jsonify(
        html=render_template("modules/login.html"),
        token=generate_auth_token(verified["username"]),
    )

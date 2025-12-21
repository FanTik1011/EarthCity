import os
from flask import Blueprint, render_template, current_app, send_from_directory

pages_bp = Blueprint("pages_bp", __name__)

@pages_bp.get("/")
def globe_page():
    return render_template("globe_auth.html")

@pages_bp.get("/favicon.ico")
def favicon():
    static_path = current_app.static_folder
    if static_path and os.path.exists(os.path.join(static_path, "favicon.ico")):
        return send_from_directory(static_path, "favicon.ico")
    return ("", 204)

import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///sola_portal.db").replace("postgres://", "postgresql+psycopg://", 1).replace("postgresql://", "postgresql+psycopg://", 1)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
app.config["SESSION_REFRESH_EACH_REQUEST"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("HTTPS_ONLY", "1") == "1"
db = SQLAlchemy(app)


def now():
    return datetime.now(timezone.utc)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(40), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(60), default="")
    bio = db.Column(db.String(400), default="")
    avatar = db.Column(db.Text, default="")
    role = db.Column(db.String(12), default="user")
    created_at = db.Column(db.DateTime(timezone=True), default=now)


class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(200), default="")
    url = db.Column(db.String(500), nullable=False)
    health_url = db.Column(db.String(500), default="")
    icon = db.Column(db.String(40), default="grid")
    published = db.Column(db.Boolean, default=True)
    position = db.Column(db.Integer, default=0)


class News(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    body = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(30), nullable=False, default="general")
    important = db.Column(db.Boolean, default=False)
    published_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=now)


class NewsRead(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    news_id = db.Column(db.Integer, db.ForeignKey("news.id"), nullable=False)
    __table_args__ = (db.UniqueConstraint("user_id", "news_id"),)


class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    name = db.Column(db.String(80), default="")
    category = db.Column(db.String(30), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now)


def user():
    return db.session.get(User, session.get("uid")) if session.get("uid") else None


def require_login():
    current = user()
    if not current:
        abort(401)
    return current


def require_owner():
    current = require_login()
    if current.role != "owner":
        abort(403)
    return current


def valid_url(value):
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password


def visible_news():
    stamp = now().replace(tzinfo=None)
    return News.query.filter(News.published_at <= stamp).filter((News.expires_at.is_(None)) | (News.expires_at > stamp)).order_by(News.important.desc(), News.published_at.desc())


@app.context_processor
def inject():
    current = user()
    unread = 0
    if current:
        unread = visible_news().filter(~News.id.in_(db.session.query(NewsRead.news_id).filter_by(user_id=current.id))).count()
    return {"current_user": current, "unread_count": unread}


@app.before_request
def csrf_check():
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        submitted = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not secrets.compare_digest(submitted or "", session.get("csrf", "")):
            abort(400)


@app.context_processor
def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return {"csrf_token": session["csrf"]}


@app.get("/")
def home():
    services = Service.query.filter_by(published=True).order_by(Service.position, Service.id).all()
    news = visible_news().limit(3).all()
    return render_template("index.html", page="home", services=services, news=news)


@app.get("/chat")
def open_chat():
    address = os.environ.get("SOLA_CHAT_URL", "https://sola-chat-web.onrender.com")
    if not valid_url(address):
        abort(503)
    session["recent_service"] = "chat"
    return redirect(address, code=302)


@app.get("/talk")
def open_talk():
    address = os.environ.get("SOLA_TALK_URL", "https://sola-talk.onrender.com/").strip()
    if not valid_url(address):
        return render_template("service_pending.html", page="services", service_name="SOLA TALK"), 503
    session["recent_service"] = "talk"
    return redirect(address, code=302)


@app.get("/download")
def open_download():
    address = os.environ.get("SOLA_DOWNLOAD_URL", "https://sola-download.onrender.com/").strip()
    if not valid_url(address):
        return render_template("service_pending.html", page="services", service_name="SOLA DOWNLOAD"), 503
    session["recent_service"] = "download"
    return redirect(address, code=302)


@app.get("/services")
def services_page():
    return render_template("services.html", page="services", services=Service.query.filter_by(published=True).order_by(Service.position, Service.id).all())


@app.get("/go/<int:service_id>")
def go(service_id):
    service = db.get_or_404(Service, service_id)
    if not service.published:
        abort(404)
    session["recent_service"] = service.id
    if service.name == "SOLA CHAT":
        return redirect(url_for("open_chat"))
    if service.name == "SOLA TALK":
        return redirect(url_for("open_talk"))
    if service.name == "SOLA DOWNLOAD":
        return redirect(url_for("open_download"))
    if not valid_url(service.url):
        abort(404)
    return redirect(service.url)


@app.get("/news")
def news_page():
    items = visible_news().all()
    read_ids = {r.news_id for r in NewsRead.query.filter_by(user_id=user().id).all()} if user() else set()
    return render_template("news.html", page="news", news=items, read_ids=read_ids)


@app.route("/news/<int:news_id>", methods=["GET", "POST"])
def news_detail(news_id):
    item = db.get_or_404(News, news_id)
    if item not in visible_news().all():
        abort(404)
    if user() and not NewsRead.query.filter_by(user_id=user().id, news_id=item.id).first():
        db.session.add(NewsRead(user_id=user().id, news_id=item.id))
        db.session.commit()
    return render_template("news_detail.html", page="news", item=item)


@app.get("/status")
def status_page():
    services = Service.query.filter_by(published=True).order_by(Service.position, Service.id).all()
    return render_template("status.html", page="status", services=services)


@app.get("/api/status")
def status_api():
    # All checks are constrained to URLs supplied by the owner; avoid server-side requests
    # to arbitrary user inputs or private infrastructure.
    return jsonify({"services": [{"id": s.id, "name": s.name, "status": "not_configured" if not s.health_url else "unknown"} for s in Service.query.filter_by(published=True)]})


@app.route("/support", methods=["GET", "POST"])
def support():
    if request.method == "POST":
        category = request.form.get("category", "other")
        body = request.form.get("body", "").strip()
        name = request.form.get("name", "").strip()[:80]
        if category not in ("bug", "question", "other") or not (10 <= len(body) <= 3000):
            flash("内容を10〜3000文字で入力してね。", "error")
        else:
            db.session.add(Ticket(user_id=user().id if user() else None, name=name, category=category, body=body))
            db.session.commit()
            flash("お問い合わせを受け付けたよ。", "ok")
            return redirect(url_for("support"))
    return render_template("support.html", page="support")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not re.fullmatch(r"[A-Za-z0-9_]{3,30}", username) or len(password) < 6:
            flash("ユーザー名は英数字と_で3〜30文字、パスワードは6文字以上にしてね。", "error")
        elif User.query.filter_by(username=username).first():
            flash("そのユーザー名は使われているよ。", "error")
        else:
            account = User(username=username, password_hash=generate_password_hash(password), display_name=username, role="user")
            db.session.add(account)
            db.session.commit()
            session.clear()
            session["uid"] = account.id
            session.permanent = True
            session["csrf"] = secrets.token_urlsafe(32)
            flash("登録できたよ。", "ok")
            return redirect(url_for("home"))
    return render_template("auth.html", page="profile", mode="register")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        account = User.query.filter_by(username=request.form.get("username", "").strip()).first()
        if not account or not check_password_hash(account.password_hash, request.form.get("password", "")):
            flash("ログイン情報を確認してね。", "error")
        else:
            session.clear()
            session["uid"] = account.id
            session["csrf"] = secrets.token_urlsafe(32)
            return redirect(url_for("home"))
    return render_template("auth.html", page="profile", mode="login")


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/profile", methods=["GET", "POST"])
def profile():
    current = require_login()
    if request.method == "POST":
        current.display_name = request.form.get("display_name", "").strip()[:60]
        current.bio = request.form.get("bio", "").strip()[:400]
        avatar = request.form.get("avatar", "")
        if avatar and len(avatar) <= 500000 and avatar.startswith("data:image/") and ";base64," in avatar:
            current.avatar = avatar
        db.session.commit()
        flash("プロフィールを保存したよ。", "ok")
        return redirect(url_for("profile"))
    return render_template("profile.html", page="profile")


@app.get("/settings")
def settings():
    return render_template("settings.html", page="settings")


@app.route("/admin", methods=["GET", "POST"])
def admin():
    require_owner()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "news":
            title = request.form.get("title", "").strip()[:150]
            body = request.form.get("body", "").strip()[:10000]
            category = request.form.get("category", "general")
            try:
                published = datetime.fromisoformat(request.form.get("published_at", "")) if request.form.get("published_at") else now().replace(tzinfo=None)
                expires = datetime.fromisoformat(request.form.get("expires_at", "")) if request.form.get("expires_at") else None
            except ValueError:
                published = now().replace(tzinfo=None)
                expires = None
            if title and body and category in ("general", "update", "maintenance", "incident") and (not expires or expires > published):
                db.session.add(News(title=title, body=body, category=category, important=bool(request.form.get("important")), published_at=published, expires_at=expires))
                db.session.commit()
                flash("お知らせを登録したよ。", "ok")
            else:
                flash("入力内容を確認してね。", "error")
        elif action == "service":
            name = request.form.get("name", "").strip()[:80]
            address = request.form.get("url", "").strip()[:500]
            if name and valid_url(address):
                db.session.add(Service(name=name, url=address, description=request.form.get("description", "")[:200], icon=request.form.get("icon", "grid")[:40], published=True, position=Service.query.count()))
                db.session.commit()
                flash("サービスを追加したよ。", "ok")
            else:
                flash("HTTPSのURLとサービス名を入力してね。", "error")
        return redirect(url_for("admin"))
    return render_template("admin.html", page="admin", services=Service.query.order_by(Service.position).all(), news=News.query.order_by(News.created_at.desc()).all(), tickets=Ticket.query.order_by(Ticket.created_at.desc()).limit(50).all())


@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "sola-portal"})


with app.app_context():
    db.create_all()
    if not Service.query.first():
        db.session.add_all([
            Service(name="SOLA CHAT", description="メッセージやグループでつながろう", url="/chat", icon="chat", position=0),
            Service(name="SOLA TALK", description="音声とビデオで会話しよう", url="/talk", icon="video", position=1, published=True),
        ])
        db.session.commit()
    # Keep the initial service entries in sync across existing databases.
    chat_service = Service.query.filter_by(name="SOLA CHAT").first()
    if chat_service:
        chat_service.url = "/chat"
        chat_service.published = True
    talk_service = Service.query.filter_by(name="SOLA TALK").first()
    if talk_service:
        talk_service.url = "/talk"
        talk_service.published = True
    else:
        db.session.add(Service(name="SOLA TALK", description="音声とビデオで会話しよう", url="/talk", icon="video", position=1, published=True))
    download_service = Service.query.filter_by(name="SOLA DOWNLOAD").first()
    if download_service:
        download_service.url = "/download"
        download_service.health_url = "https://sola-download.onrender.com/health"
        download_service.published = True
    else:
        db.session.add(Service(name="SOLA DOWNLOAD", description="Scratch作品の保存と画像ファイル変換", url="/download", health_url="https://sola-download.onrender.com/health", icon="download", position=2, published=True))
    db.session.commit()
    owner_name = os.environ.get("PORTAL_OWNER_USERNAME", "")
    owner_pass = os.environ.get("PORTAL_OWNER_PASSWORD", "")
    if owner_name and owner_pass and len(owner_pass) >= 12:
        owner = User.query.filter_by(username=owner_name).first()
        if not owner:
            db.session.add(User(username=owner_name, password_hash=generate_password_hash(owner_pass), display_name="SOLA 管理者", role="owner"))
            db.session.commit()


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=int(os.environ.get("PORT", 5000)))

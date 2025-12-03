from flask import Flask, redirect, url_for
from auth_routes import auth_bp
from teacher_routes import teacher_bp
from admin_routes import admin_bp
from student_routes import student_bp
from models import User, SessionLocal
from apscheduler.schedulers.background import BackgroundScheduler
from update_prices import update_stock_prices
from flask_cors import CORS
from api_routes import api

app = Flask(__name__)

# CORS aktivieren (MUSS DRIN SEIN)
CORS(app)

# Session-Key
app.secret_key = "SESSION_SECRET_KEY_HIER"

# JWT Secret
app.config["SECRET_KEY"] = "JWT_SUPER_SECRET_KEY_HIER"

# Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(teacher_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(student_bp)

# API Blueprint
app.register_blueprint(api)

@app.route("/")
def index():
     return redirect(url_for("auth.login"))

@app.route("/debug-users")
def debug_users():
     db = SessionLocal()
     users = db.query(User).all()
     db.close()
     return "<br>".join([f"{u.id}: {u.username or u.email} ({u.role})" 
for u in users])

# Start price updater
for _ in range(5):
     update_stock_prices()

scheduler = BackgroundScheduler()
scheduler.add_job(func=update_stock_prices, trigger="interval", hours=1)
scheduler.start()

# Öffnet alle IP-Adressen für Requests und entfernt debug mode
if __name__ == "__main__":
     app.run(host="0.0.0.0", port=5001)
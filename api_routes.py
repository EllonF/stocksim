from flask import Blueprint, request, jsonify, g, current_app
from models import (
    User, SessionLocal, Stock, StudentStock,
    Trade, StockPriceHistory
)
from functools import wraps
from collections import defaultdict
import jwt
from datetime import datetime, timedelta

api = Blueprint("api", __name__, url_prefix="/api")

# --- JWT ---
def create_token(user):
    payload = {
        "user_id": user.id,
        "role": user.role,
        "exp": datetime.utcnow() + timedelta(hours=2)
    }
    token = jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")
    return token

def token_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            auth_header = request.headers.get("Authorization")
            if not auth_header:
                return jsonify({"error": "Token missing"}), 401
            parts = auth_header.split()
            if len(parts) != 2 or parts[0] != "Bearer":
                return jsonify({"error": "Invalid token format"}), 401
            token = parts[1]
            try:
                data = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
                db = SessionLocal()
                user = db.query(User).get(data["user_id"])
                db.close()
                if not user or (role and user.role != role):
                    return jsonify({"error": "Unauthorized"}), 403
                g.current_user = user
            except jwt.ExpiredSignatureError:
                return jsonify({"error": "Token expired"}), 401
            except Exception as e:
                return jsonify({"error": "Token invalid", "msg": str(e)}), 401
            return f(*args, **kwargs)
        return decorated
    return decorator

# --- Auth: Teacher Login ---
@api.route("/auth/teacher/login", methods=["POST"])
def teacher_login():
    data = request.get_json() or {}
    username_or_email = data.get("username") or data.get("email")
    password = data.get("password")
    if not username_or_email or not password:
        return jsonify({"error": "Missing credentials"}), 400

    db = SessionLocal()
    user = db.query(User).filter(
        ((User.username == username_or_email) | (User.email == username_or_email)) &
        (User.password == password) &
        (User.role.in_(["teacher", "admin"]))
    ).first()
    db.close()

    if not user:
        return jsonify({"error": "Invalid login"}), 401

    token = create_token(user)
    return jsonify({"token": token, "role": user.role})

# --- Auth: Student Login ---
@api.route("/auth/student/login", methods=["POST"])
def student_login():
    data = request.get_json() or {}
    username = data.get("username")
    password = data.get("password")
    teacher_username = data.get("teacher_username")
    if not username or not password or not teacher_username:
        return jsonify({"error": "Missing credentials"}), 400

    db = SessionLocal()
    teacher = db.query(User).filter_by(username=teacher_username, role="teacher").first()
    if teacher:
        user = db.query(User).filter_by(
            username=username,
            password=password,
            role="student",
            teacher_id=teacher.id
        ).first()
    else:
        user = None
    db.close()
    if not user:
        return jsonify({"error": "Invalid username, password or teacher"}), 401

    token = create_token(user)
    return jsonify({"token": token, "role": user.role})


# --- STOCK ROUTES (for students) ---
@api.route("/student/dashboard")
@token_required(role="student")
def student_dashboard():
    db = SessionLocal()
    user = db.query(User).get(g.current_user.id)
    invested = 0.0
    for holding in db.query(StudentStock).filter_by(student_id=user.id).all():
        stock = db.query(Stock).get(holding.stock_id)
        if stock:
            invested += holding.quantity * stock.current_price
    result = {
        "usable_funds": round(user.funds, 2),
        "invested": round(invested, 2)
    }
    db.close()
    return jsonify(result)

@api.route("/stocks/all")
@token_required(role="student")
def get_all_stocks():
    db = SessionLocal()
    stocks = db.query(Stock).all()
    db.close()
    return jsonify([{
        "id": s.id, "symbol": s.symbol, "name": s.name, "current_price": s.current_price
    } for s in stocks])

@api.route("/stocks/<int:stock_id>")
@token_required(role="student")
def get_stock(stock_id):
    db = SessionLocal()
    stock = db.query(Stock).get(stock_id)
    db.close()
    if not stock:
        return jsonify({"error": "Stock not found"}), 404
    return jsonify({
        "id": stock.id, "symbol": stock.symbol, "name": stock.name, "current_price": stock.current_price
    })

@api.route("/stocks/<int:stock_id>/buy", methods=["POST"])
@token_required(role="student")
def buy_stock(stock_id):
    data = request.get_json() or {}
    amount = int(data.get("amount", 0))
    if amount <= 0:
        return jsonify({"error": "Invalid amount"}), 400

    db = SessionLocal()
    user = db.query(User).get(g.current_user.id)
    stock = db.query(Stock).get(stock_id)
    if not stock:
        db.close()
        return jsonify({"error": "Stock not found"}), 404

    total_cost = amount * stock.current_price
    if total_cost > user.funds:
        db.close()
        return jsonify({"error": "Not enough funds"}), 400

    holding = db.query(StudentStock).filter_by(student_id=user.id, stock_id=stock.id).first()
    if holding:
        holding.quantity += amount
    else:
        holding = StudentStock(student_id=user.id, stock_id=stock.id, quantity=amount)
        db.add(holding)

    trade = Trade(student_id=user.id, stock_id=stock.id, quantity=amount,
                  price_at_trade=stock.current_price, trade_type="buy")
    db.add(trade)
    user.funds -= total_cost
    db.commit()
    db.close()
    return jsonify({"message": "Stock purchased successfully"})


@api.route("/stocks/<int:stock_id>/sell", methods=["POST"])
@token_required(role="student")
def sell_stock(stock_id):
    data = request.get_json() or {}
    amount = int(data.get("amount", 0))
    if amount <= 0:
        return jsonify({"error": "Invalid amount"}), 400

    db = SessionLocal()
    user = db.query(User).get(g.current_user.id)
    stock = db.query(Stock).get(stock_id)
    holding = db.query(StudentStock).filter_by(student_id=user.id, stock_id=stock_id).first()
    if not stock or not holding or holding.quantity < amount:
        db.close()
        return jsonify({"error": "Not enough shares"}), 400

    holding.quantity -= amount
    if holding.quantity == 0:
        db.delete(holding)

    trade = Trade(student_id=user.id, stock_id=stock.id, quantity=amount,
                  price_at_trade=stock.current_price, trade_type="sell")
    db.add(trade)
    user.funds += amount * stock.current_price
    db.commit()
    db.close()
    return jsonify({"message": "Stock sold successfully"})


# --- STUDENT PORTFOLIO HISTORY ---
@api.route("/student/portfolio-history")
@token_required(role="student")
def student_portfolio_history():
    db = SessionLocal()
    trades = db.query(Trade).filter_by(student_id=g.current_user.id).order_by(Trade.timestamp.asc()).all()
    if not trades:
        db.close()
        return jsonify([])

    stock_ids = sorted({t.stock_id for t in trades})
    histories = {}
    all_timestamps = set()
    for sid in stock_ids:
        hist = db.query(StockPriceHistory).filter_by(stock_id=sid).order_by(StockPriceHistory.timestamp.asc()).all()
        histories[sid] = hist
        for h in hist:
            all_timestamps.add(h.timestamp)
    for t in trades:
        all_timestamps.add(t.timestamp)
    sorted_ts = sorted(all_timestamps)

    from collections import defaultdict
    holdings = defaultdict(int)
    trade_idx = 0
    price_ptr = {sid: 0 for sid in stock_ids}
    current_price = {sid: (histories[sid][0].price if histories[sid] else 0) for sid in stock_ids}

    results = []
    for ts in sorted_ts:
        for sid in stock_ids:
            hist = histories[sid]
            ptr = price_ptr[sid]
            while ptr < len(hist) and hist[ptr].timestamp <= ts:
                current_price[sid] = hist[ptr].price
                ptr += 1
            price_ptr[sid] = ptr
        while trade_idx < len(trades) and trades[trade_idx].timestamp <= ts:
            tr = trades[trade_idx]
            holdings[tr.stock_id] += tr.quantity if tr.trade_type == "buy" else -tr.quantity
            trade_idx += 1
        total_value = sum(holdings[sid] * current_price[sid] for sid in holdings if holdings[sid] > 0)
        results.append({"timestamp": ts.strftime("%Y-%m-%d %H:%M"), "value": round(total_value, 2)})
    db.close()
    return jsonify(results)


# --- TEACHER: CRUD STUDENTS ---
@api.route("/teacher/add-student", methods=["POST"])
@token_required(role="teacher")
def add_student():
    data = request.get_json() or {}
    username = data.get("username")
    password = data.get("password")
    funds = float(data.get("funds", 0))
    if not username or not password:
        return jsonify({"error": "Missing username or password"}), 400

    db = SessionLocal()
    if db.query(User).filter_by(username=username, teacher_id=g.current_user.id).first():
        db.close()
        return jsonify({"error": "Student already exists"}), 400

    student = User(username=username, password=password, role="student",
                   funds=funds, teacher_id=g.current_user.id)
    db.add(student)
    db.commit()
    db.close()
    return jsonify({"success": f"Student {username} added"})


# --- Teacher: Get student's portfolio ---
@api.route("/teacher/student-portfolio/<int:student_id>")
@token_required(role="teacher")
def teacher_student_portfolio(student_id):
    db = SessionLocal()
    student = db.query(User).filter_by(id=student_id, role="student",
                                       teacher_id=g.current_user.id).first()
    if not student:
        db.close()
        return jsonify({"error": "Student not found"}), 404

    portfolio = []
    for h in student.holdings:
        stock = h.stock
        trades = db.query(Trade).filter_by(student_id=student.id, stock_id=stock.id, trade_type="buy").all()
        total_paid = sum(tr.quantity * tr.price_at_trade for tr in trades)
        portfolio.append({
            "stock_id": stock.id, "symbol": stock.symbol, "name": stock.name,
            "quantity": h.quantity, "current_price": stock.current_price,
            "total_value": round(h.quantity * stock.current_price, 2),
            "total_paid": round(total_paid, 2)
        })
    db.close()
    return jsonify({"portfolio": portfolio})

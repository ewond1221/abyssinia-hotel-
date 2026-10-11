import logging
import os
import secrets
from datetime import datetime, timedelta, date, timezone
from functools import wraps

import jwt
from flask import Flask, redirect, render_template, jsonify, request
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

from orders import db, Order, Admin, MenuItem, Booking
from security import (
    IS_PRODUCTION, LOGIN_FAIL_WINDOW, apply_security_headers, check_limit, clean_int, clean_menu_fields,
    clean_number, clean_text, client_ip, is_known_default_password, login_locked, password_problem,
    rate_limit, record_failed_login, too_many_requests,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("hotel")

app = Flask(__name__, static_folder="public/static")

# ---------------------------------------------------------------------------
# Secrets: read from environment variables on the SERVER only.
# Nothing here is ever sent to the browser, and there are no default secrets.
# ---------------------------------------------------------------------------
_WEAK_SECRETS = {"", "abcdefg", "secret", "changeme", "your-secret-key"}
_jwt_secret = os.environ.get("JWT_SECRET_KEY", "")

if IS_PRODUCTION:
    if _jwt_secret in _WEAK_SECRETS or len(_jwt_secret) < 32:
        raise RuntimeError(
            "JWT_SECRET_KEY is missing or too weak. In Vercel go to Settings > Environment Variables "
            "and set it to a random string of at least 32 characters."
        )
elif _jwt_secret in _WEAK_SECRETS:
    _jwt_secret = secrets.token_urlsafe(48)  # local development only; changes on every restart

app.config["JWT_SECRET_KEY"] = _jwt_secret

# Reject oversized request bodies before they are even parsed (cheap protection against abuse).
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024

default_database = "sqlite:////tmp/orders.db" if os.environ.get("VERCEL") else "sqlite:///orders.db"
database_url = os.environ.get("DATABASE_URL", default_database)

# Use the psycopg2 driver explicitly (it is the one in requirements.txt). Without this,
# newer SQLAlchemy versions look for a different driver and the site fails to start.
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)

engine_options = {"pool_pre_ping": True}
if database_url.startswith("postgresql"):
    # Keep each serverless instance's connection count small so a traffic spike
    # cannot exhaust the database's connection limit.
    engine_options.update(pool_size=2, max_overflow=3, pool_recycle=300)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = engine_options
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

ROOMS = {
    "standard": {
        "name": "Standard Room",
        "price": 4500,
        "total": 6,
        "max_guests": 2,
        "img": "img/hotel/standard.jpg",
        "desc": "A calm room with a plush bed, Ethiopian textile art, and a balcony facing the mountains."
    },
    "deluxe": {
        "name": "Deluxe Room",
        "price": 6500,
        "total": 4,
        "max_guests": 3,
        "img": "img/hotel/deluxe.jpg",
        "desc": "More space with a work desk, an armchair, and wide windows over the city and mountains."
    }
}

@app.before_request
def global_api_limit():
    """Broad per-IP cap on every API call. Stricter caps are added per endpoint below."""
    if request.path.startswith("/api/"):
        return check_limit("api", 300, 60)


@app.after_request
def add_security_headers(response):
    return apply_security_headers(response)


@app.errorhandler(HTTPException)
def handle_http_error(error):
    if request.path.startswith("/api/"):
        messages = {404: "Not found", 405: "Method not allowed", 413: "Request is too large"}
        response = jsonify({"error": messages.get(error.code, error.description)})
        response.status_code = error.code
        return response
    return error


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    # Log the real error on the server, but never show stack traces or internals to visitors.
    log.exception("Unhandled error on %s %s", request.method, request.path)
    try:
        db.session.rollback()
    except Exception:
        pass
    if request.path.startswith("/api/"):
        return jsonify({"error": "Something went wrong. Please try again."}), 500
    return "Something went wrong.", 500


def admin_required(f):

    @wraps(f)
    def decorated_function(*args, **kwargs):

       auth_header = request.headers.get("Authorization")

       if not auth_header:
            return jsonify({
                "error": "Authorization token is required"
            }), 401

       parts = auth_header.split(" ")

       if len(parts) != 2 or parts[0] != "Bearer" or not parts[1]:
            return jsonify({
                "error": "Invalid token"
            }), 401

       token = parts[1]

       try:
            payload = jwt.decode(
                token,
                app.config["JWT_SECRET_KEY"],
                algorithms=["HS256"],
                options={"require": ["exp"]}
            )

       except jwt.ExpiredSignatureError:
            return jsonify({
                "error": "Token has expired"
            }), 401

       except jwt.InvalidTokenError:
            return jsonify({
                "error": "Invalid token"
            }), 401

       if payload.get("role") != "admin":
            return jsonify({
                "error": "Admin permission required"
            }), 403

       # The account must still exist (deleting an admin revokes their token immediately).
       if db.session.get(Admin, payload.get("admin_id")) is None:
            return jsonify({
                "error": "Invalid token"
            }), 401

       return f(*args, **kwargs)

    return decorated_function

@app.route("/")
def landing():
    return render_template("landing.html", rooms=ROOMS)

@app.route("/menu")
def home():
    return render_template("index.html")

@app.route("/rooms")
def rooms_page():
    return render_template("rooms.html", rooms=ROOMS)

@app.route("/booking-status")
def booking_status():
    return render_template("booking-status.html")

@app.route("/admin/bookings")
def admin_bookings_page():
    return render_template("admin_bookings.html")

@app.route("/admin/login")
def admin_login_page():
    return render_template("admin_login.html")
@app.route("/admin/dashboard")
def admin_dashboard():
    return render_template("admin_dashboard.html")
@app.route("/cart.html")
def cart():
    return render_template("cart.html")

@app.route("/order-status")
def order_status():
    return render_template("order-status.html")

@app.route("/api/admin/orders/<int:order_id>/status", methods=["PATCH"])
@admin_required
def update_order_status(order_id):
    order = db.session.get(Order, order_id)

    if not order:
        return jsonify({
            "error": "Order not found"
        }), 404

    data = request.get_json(silent=True) or {}

    status = data.get("status")

    allowed_statuses = [
        "pending",
        "preparing",
        "completed"
    ]

    if status not in allowed_statuses:
        return jsonify({
            "error": "Invalid order status"
        }), 400

    order.status = status

    db.session.commit()

    return jsonify({
        "message": "Order status updated successfully",
        "order": {
            "id": order.id,
            "status": order.status
        }
    }), 200


@app.route("/api/admin/orders/<int:order_id>", methods=["DELETE"])
@admin_required
def delete_order(order_id):
    order = db.session.get(Order, order_id)

    if order is None:
        return jsonify({
            "error": f"No order found with ID {order_id}"
        }), 404

    db.session.delete(order)
    db.session.commit()

    return jsonify({
        "message": "Order deleted successfully"
    }), 200

@app.route("/api/orders/<int:order_id>", methods=["GET"])
@rate_limit("order-lookup", 15, 60)
@rate_limit("order-lookup-hour", 100, 3600)
def get_order(order_id):

    customer = (request.args.get("customer") or "").strip()[:100]

    if not customer:
        return jsonify({
            "error": "Order ID and customer name are both required"
        }), 400

    order = db.session.get(Order, order_id)

    if order is None or order.customer.strip().lower() != customer.lower():
        return jsonify({
            "error": "No matching order found for that ID and name"
        }), 404

    return jsonify({
        "id": order.id,
        "customer": order.customer,
        "items": order.items,
        "quantity": order.quantity,
        "total_price": order.total_price,
        "created_at": order.created_at.isoformat(),
        "status": order.status
    })

@app.route("/admin/add")
def admin_add_page():
    return render_template("admin_add.html")

@app.route("/admin/menu")
def admin_menu_page():
    return render_template("admin_menu.html")

MAX_ORDER_LINES = 25
MAX_QTY_PER_LINE = 20
MAX_ORDER_QUANTITY = 100
MAX_ORDER_TOTAL = 100_000


def build_order_from_entries(entries, allow_custom=False):
    """
    Turns a list of item entries into a validated (items_text, quantity, total_price)
    tuple. Prices and names for catalog items always come from the MenuItem table,
    never from the client, so the total can never be spoofed by a bad request body.
    Size limits stop a single request from creating a giant order.

    entries: list of dicts, each either
        {"item_id": "<menu item id>", "qty": <int>}                     -> catalog item
        {"custom": true, "name": "<str>", "price": <number>, "qty": <int>}  -> custom item (admin only)
    Raises ValueError with a user-facing message on any problem.
    """
    if not entries or not isinstance(entries, list):
        raise ValueError("At least one item is required")

    if len(entries) > MAX_ORDER_LINES:
        raise ValueError(f"An order can have at most {MAX_ORDER_LINES} different items")

    # One query for every catalog item, instead of one query per line.
    wanted_ids = {
        entry.get("item_id")
        for entry in entries
        if isinstance(entry, dict) and not entry.get("custom") and isinstance(entry.get("item_id"), str)
    }
    catalog = {}
    if wanted_ids:
        catalog = {m.item_id: m for m in MenuItem.query.filter(MenuItem.item_id.in_(wanted_ids)).all()}

    line_parts = []
    quantity = 0
    total_price = 0.0

    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Invalid item format")

        qty = clean_int(entry.get("qty"), "Item quantity", 1, MAX_QTY_PER_LINE)

        if entry.get("custom"):
            if not allow_custom:
                raise ValueError("Custom items are not allowed for this order type")

            name = clean_text(entry.get("name"), "Custom item name", 100)
            price = clean_number(entry.get("price"), f"Price for '{name}'", 0, 100_000)
        else:
            item_id = entry.get("item_id")
            if not item_id or not isinstance(item_id, str):
                raise ValueError("A menu item is required")

            menu_item = catalog.get(item_id)
            if not menu_item:
                raise ValueError(f"Menu item '{item_id[:50]}' was not found")

            name = menu_item.name
            price = menu_item.price

        quantity += qty
        if quantity > MAX_ORDER_QUANTITY:
            raise ValueError(f"An order can have at most {MAX_ORDER_QUANTITY} items in total")

        total_price += price * qty
        line_parts.append(f"{name} x{qty}")

    if total_price > MAX_ORDER_TOTAL:
        raise ValueError("Order total is too large")

    return ", ".join(line_parts), quantity, round(total_price, 2)


@app.route("/api/admin/orders", methods=["POST"])
@admin_required
def admin_create_order():
    data = request.get_json(silent=True) or {}

    try:
        customer = clean_text(data.get("customer"), "Customer name", 100)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    try:
        items_text, quantity, total_price = build_order_from_entries(
            data.get("items"), allow_custom=True
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    order = Order(
        customer=customer,
        items=items_text,
        quantity=quantity,
        total_price=total_price
    )

    db.session.add(order)
    db.session.commit()

    return jsonify({
        "message": "Order created successfully",
        "order": {
            "id": order.id,
            "customer": order.customer,
            "items": order.items,
            "quantity": order.quantity,
            "total_price": order.total_price,
            "status": order.status
        }
    }), 201

@app.route("/api/orders", methods=["POST"])
@rate_limit("order-create", 10, 600)
@rate_limit("order-create-day", 60, 86400)
def create_order():
    data = request.get_json(silent=True) or {}

    try:
        customer = clean_text(data.get("customer"), "Customer name", 100)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    try:
        # Customers may only order real menu items - no custom/freeform entries.
        items_text, quantity, total_price = build_order_from_entries(
            data.get("items"), allow_custom=False
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    order = Order(
        customer=customer,
        items=items_text,
        quantity=quantity,
        total_price=total_price
    )

    db.session.add(order)
    db.session.commit()

    return jsonify({
        "message": "Order created successfully",
        "order": {
            "id": order.id,
            "customer": order.customer,
            "items": order.items,
            "quantity": order.quantity,
            "total_price": order.total_price,
            "status": order.status
        }
    }), 201


@app.route("/api/admin/orders", methods=["GET"])
@admin_required
def get_orders():
    orders = Order.query.all()

    return jsonify([
        {
            "id": order.id,
            "customer": order.customer,
            "items": order.items,
            "quantity": order.quantity,
            "total_price": order.total_price,
            "created_at": order.created_at.isoformat(),
            "status": order.status
        }
        for order in orders
    ])

DEFAULT_MENU = [
    {"id": "bruschetta", "name": "Classic Bruschetta", "desc": "Toasted sourdough topped with vine tomatoes, fresh basil, and a drizzle of extra-virgin olive oil.", "price": 8.5, "img": "img/image1.png", "category": "starters"},
    {"id": "mushroom-soup", "name": "Cream of Mushroom Soup", "desc": "Rich, velvety mushroom soup with a swirl of cream and fresh thyme garnish.", "price": 7.0, "img": "img/image2.png", "category": "starters"},
    {"id": "shrimp-cocktail", "name": "Shrimp Cocktail", "desc": "Chilled jumbo shrimp served with house-made cocktail sauce and lemon wedges.", "price": 13.0, "img": "img/image3.png", "category": "starters"},
    {"id": "ribeye-steak", "name": "Grilled Ribeye Steak", "desc": "12 oz prime ribeye, seasoned and flame-grilled, served with roasted potatoes and seasonal vegetables.", "price": 38.0, "img": "img/image4.png", "category": "main-course"},
    {"id": "pan-seared-salmon", "name": "Pan-Seared Salmon", "desc": "Atlantic salmon fillet with lemon-dill butter sauce, served over wild rice and steamed asparagus.", "price": 29.0, "img": "img/image5.png", "category": "main-course"},
    {"id": "truffle-pasta", "name": "Truffle Pasta", "desc": "House-made tagliatelle tossed in a black truffle cream sauce with parmesan and fresh parsley.", "price": 24.0, "img": "img/image5.png", "category": "main-course"},
    {"id": "roast-chicken", "name": "Herb Roast Chicken", "desc": "Half chicken slow-roasted with rosemary, garlic, and lemon, served with mashed potatoes and gravy.", "price": 22.0, "img": "img/image6.png", "category": "main-course"},
    {"id": "lava-cake", "name": "Chocolate Lava Cake", "desc": "Warm dark chocolate fondant with a molten centre, served with vanilla bean ice cream.", "price": 11.0, "img": "img/image7.png", "category": "desserts"},
    {"id": "creme-brulee", "name": "Crème Brûlée", "desc": "Classic French custard with a crisp caramelised sugar crust, topped with fresh berries.", "price": 10.0, "img": "img/image8.png", "category": "desserts"},
    {"id": "cheesecake", "name": "New York Cheesecake", "desc": "Dense and creamy cheesecake on a buttery graham cracker base with a fresh strawberry compote.", "price": 9.5, "img": "img/image9.png", "category": "desserts"},
    {"id": "doro-wat", "name": "Doro Wat", "desc": "Slow-cooked chicken stew in spiced berbere sauce with a boiled egg, served with injera.", "price": 24.0, "img": "img/hotel/cuisine.jpg", "category": "ethiopian"},
    {"id": "kitfo", "name": "Kitfo", "desc": "Minced beef seasoned with mitmita and spiced butter, served with ayib cheese and injera.", "price": 26.0, "img": "img/hotel/cuisine.jpg", "category": "ethiopian"},
    {"id": "beyaynetu", "name": "Beyaynetu Platter", "desc": "Fasting platter of shiro, misir wat, gomen, and atkilt on fresh injera.", "price": 20.0, "img": "img/hotel/cuisine.jpg", "category": "ethiopian"},
]

@app.route("/api/menu")
def get_menu():
    items = MenuItem.query.all()
    response = jsonify([item.to_dict() for item in items])
    # Let Vercel's edge cache answer repeat visitors, so most menu views never reach the database.
    response.headers["Cache-Control"] = "public, max-age=15, s-maxage=30, stale-while-revalidate=60"
    return response


@app.route("/api/admin/menu", methods=["POST"])
@admin_required
def admin_add_menu_item():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "All menu item fields are required"}), 400

    try:
        fields = clean_menu_fields(data)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    if MenuItem.query.filter_by(item_id=fields["id"]).first():
        return jsonify({"error": "A menu item with that ID already exists"}), 400

    item = MenuItem(
        item_id=fields["id"],
        name=fields["name"],
        desc=fields["desc"],
        price=fields["price"],
        img=fields["img"],
        category=fields["category"]
    )

    db.session.add(item)
    db.session.commit()

    return jsonify({"message": "Menu item added", "item": item.to_dict()}), 201


@app.route("/api/admin/menu/<item_id>", methods=["PATCH"])
@admin_required
def admin_update_menu_item(item_id):
    item = MenuItem.query.filter_by(item_id=item_id).first()

    if not item:
        return jsonify({"error": "Menu item not found"}), 404

    data = request.get_json(silent=True)
    data = dict(data) if isinstance(data, dict) else {}
    data.pop("id", None)  # an item's ID cannot be changed

    try:
        fields = clean_menu_fields(data, partial=True)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    for field, value in fields.items():
        setattr(item, field, value)

    db.session.commit()

    return jsonify({"message": "Menu item updated", "item": item.to_dict()})


@app.route("/api/admin/menu/<item_id>", methods=["DELETE"])
@admin_required
def admin_delete_menu_item(item_id):
    item = MenuItem.query.filter_by(item_id=item_id).first()

    if not item:
        return jsonify({"error": "Menu item not found"}), 404

    db.session.delete(item)
    db.session.commit()

    return jsonify({"message": "Menu item deleted"})

# Used so a login attempt for an unknown username takes as long as a real one
# (otherwise response time would reveal which usernames exist).
DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_urlsafe(16))


@app.route("/api/auth/admin/login", methods=["POST"])
@rate_limit("login-min", 5, 60, strict=True)
@rate_limit("login-hour", 30, 3600, strict=True)
def admin_login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}

    username = data.get("username")
    password = data.get("password")

    if not isinstance(username, str) or not isinstance(password, str) or not username or not password:
        return jsonify({
            "error": "Username and password are required"
        }), 400

    # Absurdly long input is never valid, and hashing it would waste server time.
    if len(username) > 100 or len(password) > 128:
        return jsonify({
            "error": "Invalid username or password"
        }), 401

    # Too many recent failures for this username (from any IP): refuse before doing any password work.
    try:
        locked = login_locked(username)
    except Exception:
        log.exception("login lockout check failed")
        return jsonify({"error": "Service temporarily unavailable. Please try again shortly."}), 503

    if locked:
        return too_many_requests(LOGIN_FAIL_WINDOW)

    admin = Admin.query.filter_by(username=username).first()

    # Always do exactly one password check, whether or not the username exists.
    stored_hash = admin.password_hash if admin else DUMMY_PASSWORD_HASH
    password_ok = check_password_hash(stored_hash, password) and admin is not None

    if not password_ok:
        try:
            record_failed_login(username)
        except Exception:
            log.exception("could not record failed login")
        log.warning("Failed admin login from %s", client_ip())
        return jsonify({
            "error": "Invalid username or password"
        }), 401

    # A site that still accepts the old default password can be taken over by anyone.
    if IS_PRODUCTION and is_known_default_password(password):
        log.warning("Admin login refused: account still uses a default password")
        return jsonify({
            "error": "This account still uses a default password. Set a new one by running: python admin.py"
        }), 403

    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "admin_id": admin.id,
            "role": admin.role,
            "iat": now,
            "exp": now + timedelta(hours=1)
        },
        app.config["JWT_SECRET_KEY"],
        algorithm="HS256"
    )

    return jsonify({
        "message": "Login successful",
        "token": token
    }), 200


MAX_STAY_NIGHTS = 30
MAX_ADVANCE_DAYS = 365


def parse_stay(check_in, check_out):
    try:
        start = date.fromisoformat(check_in)
        end = date.fromisoformat(check_out)
    except (TypeError, ValueError):
        raise ValueError("Enter valid check-in and check-out dates")

    if start < date.today():
        raise ValueError("Check-in date cannot be in the past")

    if end <= start:
        raise ValueError("Check-out must be after check-in")

    if (end - start).days > MAX_STAY_NIGHTS:
        raise ValueError(f"Stays are limited to {MAX_STAY_NIGHTS} nights")

    if start > date.today() + timedelta(days=MAX_ADVANCE_DAYS):
        raise ValueError("Check-in date is too far in the future")

    return start, end


def rooms_left(room_type, start, end):
    taken = Booking.query.filter(
        Booking.room_type == room_type,
        Booking.status != "cancelled",
        Booking.check_in < end,
        Booking.check_out > start
    ).count()

    return ROOMS[room_type]["total"] - taken


def booking_json(booking):
    return {
        "id": booking.id,
        "guest": booking.guest,
        "room_type": booking.room_type,
        "room": ROOMS[booking.room_type]["name"],
        "check_in": booking.check_in.isoformat(),
        "check_out": booking.check_out.isoformat(),
        "nights": (booking.check_out - booking.check_in).days,
        "guests": booking.guests,
        "total_price": booking.total_price,
        "status": booking.status,
        "created_at": booking.created_at.isoformat()
    }


@app.route("/api/availability")
@rate_limit("availability", 30, 60)
def availability():
    try:
        start, end = parse_stay(request.args.get("check_in"), request.args.get("check_out"))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    return jsonify({key: rooms_left(key, start, end) for key in ROOMS})


@app.route("/api/bookings", methods=["POST"])
@rate_limit("booking-create", 5, 600)
@rate_limit("booking-create-day", 20, 86400)
def create_booking():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}

    room_type = data.get("room_type")

    try:
        guest = clean_text(data.get("guest"), "Guest name", 100)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    if not isinstance(room_type, str) or room_type not in ROOMS:
        return jsonify({"error": "Choose a valid room type"}), 400

    room = ROOMS[room_type]

    try:
        guests = clean_int(data.get("guests"), "Number of guests", 1, 20)
    except ValueError:
        return jsonify({"error": "Number of guests must be a whole number"}), 400

    if guests < 1 or guests > room["max_guests"]:
        return jsonify({"error": f"{room['name']} fits 1 to {room['max_guests']} guests"}), 400

    try:
        start, end = parse_stay(data.get("check_in"), data.get("check_out"))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    if rooms_left(room_type, start, end) <= 0:
        return jsonify({"error": f"No {room['name']} available for those dates"}), 409

    booking = Booking(
        guest=guest,
        room_type=room_type,
        check_in=start,
        check_out=end,
        guests=guests,
        total_price=room["price"] * (end - start).days
    )

    db.session.add(booking)
    db.session.commit()

    return jsonify({
        "message": "Booking created successfully",
        "booking": booking_json(booking)
    }), 201


@app.route("/api/bookings/<int:booking_id>", methods=["GET"])
@rate_limit("booking-lookup", 15, 60)
@rate_limit("booking-lookup-hour", 100, 3600)
def get_booking(booking_id):
    guest = (request.args.get("guest") or "").strip()[:100]

    if not guest:
        return jsonify({"error": "Booking ID and guest name are both required"}), 400

    booking = db.session.get(Booking, booking_id)

    if booking is None or booking.guest.strip().lower() != guest.lower():
        return jsonify({"error": "No matching booking found for that ID and name"}), 404

    return jsonify(booking_json(booking))


@app.route("/api/admin/bookings", methods=["GET"])
@admin_required
def admin_get_bookings():
    bookings = Booking.query.order_by(Booking.id.desc()).all()
    return jsonify([booking_json(booking) for booking in bookings])


@app.route("/api/admin/bookings/<int:booking_id>/status", methods=["PATCH"])
@admin_required
def admin_update_booking_status(booking_id):
    booking = db.session.get(Booking, booking_id)

    if not booking:
        return jsonify({"error": "Booking not found"}), 404

    status = (request.get_json(silent=True) or {}).get("status")

    if status not in ["pending", "confirmed", "cancelled"]:
        return jsonify({"error": "Invalid booking status"}), 400

    if booking.status == "cancelled" and status != "cancelled":
        if rooms_left(booking.room_type, booking.check_in, booking.check_out) <= 0:
            return jsonify({"error": "That room type is now fully booked for these dates"}), 409

    booking.status = status
    db.session.commit()

    return jsonify({"message": "Booking status updated", "booking": booking_json(booking)})


@app.route("/api/admin/bookings/<int:booking_id>", methods=["DELETE"])
@admin_required
def admin_delete_booking(booking_id):
    booking = db.session.get(Booking, booking_id)

    if not booking:
        return jsonify({"error": "Booking not found"}), 404

    db.session.delete(booking)
    db.session.commit()

    return jsonify({"message": "Booking deleted"})


def setup_database():
    with app.app_context():
        try:
            db.create_all()

            # There is NO default admin password any more. The first admin is only created
            # when ADMIN_PASSWORD is set to a strong password (12+ characters).
            # To create or reset an admin at any time, run:  python admin.py
            if Admin.query.count() == 0:
                seed_username = os.environ.get("ADMIN_USERNAME", "admin")
                seed_password = os.environ.get("ADMIN_PASSWORD", "")
                problem = password_problem(seed_password, seed_username)

                if problem:
                    log.warning("No admin account created. Set ADMIN_PASSWORD or run `python admin.py`. (%s)", problem)
                else:
                    db.session.add(Admin(
                        username=seed_username,
                        password_hash=generate_password_hash(seed_password),
                        role="admin"
                    ))

            if MenuItem.query.count() == 0:
                for item in DEFAULT_MENU:
                    db.session.add(MenuItem(
                        item_id=item["id"],
                        name=item["name"],
                        desc=item["desc"],
                        price=item["price"],
                        img=item["img"],
                        category=item["category"]
                    ))

            db.session.commit()
        except Exception:
            db.session.rollback()


setup_database()

if __name__ == "__main__":
    # Debug mode exposes an interactive console, so it is opt-in for local use only.
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")

import os
from flask import Flask
from config import Config
from models import db
from models.city import City

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    return app

SEED_CITIES = [
    # Ukraine
    ("Lviv", "Ukraine", 49.8397, 24.0297, 78, 1240, "Medium", 12, 540000),
    ("Kyiv", "Ukraine", 50.4501, 30.5234, 82, 3100, "High", 14, 900000),
    ("Odesa", "Ukraine", 46.4825, 30.7233, 74, 1900, "Medium", 11, 420000),
    ("Dnipro", "Ukraine", 48.4647, 35.0462, 70, 1200, "Medium", 10, 300000),
    ("Kharkiv", "Ukraine", 49.9935, 36.2304, 73, 1500, "Medium", 11, 360000),

    # Poland
    ("Warsaw", "Poland", 52.2297, 21.0122, 86, 4200, "High", 13, 1200000),
    ("Krakow", "Poland", 50.0647, 19.9450, 84, 2600, "High", 12, 800000),
]

if __name__ == "__main__":
    os.makedirs(os.path.join(os.path.dirname(__file__)), exist_ok=True)

    app = create_app()
    with app.app_context():
        db.create_all()

        if City.query.count() == 0:
            for name, country, lat, lng, rating, players, safety, tax, budget in SEED_CITIES:
                db.session.add(City(
                    name=name, country=country, lat=lat, lng=lng,
                    rating=rating, players_count=players, safety_level=safety,
                    tax_percent=tax, budget=budget
                ))
            db.session.commit()
            print("✅ Database created + seeded.")
        else:
            print("ℹ️ Database already has cities, skip seed.")

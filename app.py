import os
from pathlib import Path

from flask import Flask
from flasgger import Swagger
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


def create_app():
    app = Flask(__name__)

    app.json.sort_keys = False  # type: ignore

    swagger = Swagger(app)

    from routes.teams import teams_bp
    from routes.players import players_bp
    from routes.matches import matches_bp
    from routes.news import news_bp
    from routes.results import results_bp
    from routes.demos import demos_bp
    from routes.events import events_bp

    app.register_blueprint(teams_bp)
    app.register_blueprint(players_bp)
    app.register_blueprint(matches_bp)
    app.register_blueprint(news_bp)
    app.register_blueprint(results_bp)
    app.register_blueprint(demos_bp)
    app.register_blueprint(events_bp)

    @app.get("/health")
    def health_check():
        return {"status": "ok"}, 200

    return app


flask_app = create_app()

if __name__ == "__main__":
    flask_app.run(debug=False, host="0.0.0.0", port=8000, use_reloader=False)

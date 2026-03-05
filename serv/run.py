from server import create_app
from server import auth as auth_mod
from server import files as files_mod


def main() -> None:
    app = create_app()
    app.register_blueprint(auth_mod.bp, url_prefix=app.config["BASE"])
    app.register_blueprint(files_mod.bp, url_prefix=app.config["BASE"])
    with app.app_context():
        files_mod.cleanup_local_del()
    app.run(host="0.0.0.0", port=48240, debug=False)


if __name__ == "__main__":
    main()

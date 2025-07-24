import sqlite3
import click
from flask import current_app, g

def get_db():
    """Connects to the application's configured database.
    The connection is unique per request and will be reused if called again.
    """
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row # Returns rows that behave like dicts

    return g.db

def close_db(e=None):
    """Closes the database connection at the end of the request."""
    db = g.pop('db', None)

    if db is not None:
        db.close()

def init_db():
    """Clear existing data and create new tables."""
    db = get_db()

    with current_app.open_resource('schema.sql') as f:
        # Decode the bytes to a string and execute the SQL
        db.executescript(f.read().decode('utf8'))

    # Optional: Add an admin user immediately after creating tables
    # if you want a default admin account for easy testing
    # try:
    #     from werkzeug.security import generate_password_hash
    #     db.execute(
    #         "INSERT INTO users (username, email, password, is_admin) VALUES (?, ?, ?, ?)",
    #         ("admin", "admin@example.com", generate_password_hash("adminpassword"), 1)
    #     )
    #     db.commit()
    #     print("Default admin user 'admin' created with password 'adminpassword'.")
    # except sqlite3.IntegrityError:
    #     print("Default admin user 'admin' already exists.")
    # except Exception as e:
    #     print(f"Error creating default admin user: {e}")


@click.command('init-db')
def init_db_command():
    """Clear existing data and create new tables."""
    init_db()
    click.echo('Initialized the database.')

def init_app(app):
    """Register database functions with the Flask app."""
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
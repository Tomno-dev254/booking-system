import sqlite3

import click
from flask import current_app, g

def get_db():
    """Connects to the specific database."""
    if 'db' not in g:
        # Get database path from app config
        database_path = current_app.config['DATABASE']
        # print(f"Connecting to database: {database_path}") # For debugging

        g.db = sqlite3.connect(
            database_path,
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row # This makes rows behave like dictionaries
    return g.db

def close_db(e=None):
    """Closes the database connection."""
    db = g.pop('db', None)

    if db is not None:
        db.close()

def init_db():
    """Clear existing data and create new tables."""
    db = get_db()

    # Read the schema.sql file
    with current_app.open_resource('schema.sql') as f:
        db.executescript(f.read().decode('utf8')) # Use executescript for multiple SQL statements

    click.echo('Initialized the database.') # Provides feedback to the user

def init_app(app):
    """Register database functions with the Flask app."""
    # Register close_db to be called automatically after each request
    app.teardown_appcontext(close_db)
    # Register init_db as a Flask command
    app.cli.add_command(init_db_command)

@click.command('init-db')
def init_db_command():
    """Clear existing data and create new tables."""
    init_db()
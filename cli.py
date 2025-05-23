import click
from database import create_db_and_tables
from logging_config import setup_logging, logger

@click.group()
def cli():
    """CLI for managing the application"""
    pass

@cli.command()
def init_db():
    """Initialize the database by creating all tables."""
    try:
        setup_logging()
        create_db_and_tables()
        click.echo(click.style("Database tables created successfully.", fg="green"))
    except Exception as e:
        click.echo(click.style(f"Error creating database tables: {str(e)}", fg="red"))
        raise click.Abort()

if __name__ == '__main__':
    cli() 
#!/usr/bin/env python3
import os
import sys
from pathlib import Path
import sqlite3
from alembic.config import Config
from alembic import command
import shutil
import argparse

def reset_database():
    """Reset the database by removing it and letting it be recreated"""
    db_path = Path("spizarnia.db")
    if db_path.exists():
        db_path.unlink()
    print("Database reset complete. Please restart the application.")

def apply_migrations():
    """Apply all pending migrations"""
    try:
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        print("Migrations applied successfully.")
    except Exception as e:
        print(f"Error applying migrations: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='Database Fix Tool')
    parser.add_argument('--force', action='store_true', help='Skip confirmation prompts')
    args = parser.parse_args()

    print("Database Fix Tool")
    print("1. Reset database (delete and recreate)")
    print("2. Apply migrations (keep existing data)")
    
    choice = input("Choose an option (1/2): ").strip()
    
    if choice == "1":
        if args.force or input("This will delete all data. Are you sure? (y/N): ").lower() == 'y':
            reset_database()
        else:
            print("Operation cancelled.")
    elif choice == "2":
        apply_migrations()
    else:
        print("Invalid option.")

if __name__ == "__main__":
    main() 
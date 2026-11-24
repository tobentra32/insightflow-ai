
from getpass import getpass

from app.database import SessionLocal
from app.models.user import User
from app.core.security import hash_password, validate_password


def main():

    db = SessionLocal()

    try:
        existing_admin = (
            db.query(User)
            .filter(User.role == "admin")
            .first()
        )

        if existing_admin:
            print("An administrator already exists.")
            print("Use the administrator account-management process instead.")
            return

        name = input("Administrator name: ").strip()
        email = input("Administrator email: ").strip().lower()

        if not name or not email:
            print("Name and email are required.")
            return

        existing_user = (
            db.query(User)
            .filter(User.email == email)
            .first()
        )

        if existing_user:
            print("This email address already belongs to an account.")
            return

        password = getpass("Administrator password: ")
        confirm_password = getpass("Confirm password: ")

        if password != confirm_password:
            print("Passwords do not match.")
            return

        try:
            validate_password(password)
        except ValueError as exc:
            print(str(exc))
            return

        admin = User(
            name=name,
            email=email,
            password_hash=hash_password(password),
            role="admin",
            department_id=None,
            is_active=True,
            must_change_password=False,
        )

        db.add(admin)
        db.commit()
        db.refresh(admin)

        print("\nAdministrator account created successfully.")
        print(f"User ID: {admin.id}")
        print(f"Email: {admin.email}")
        print(f"Role: {admin.role}")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()

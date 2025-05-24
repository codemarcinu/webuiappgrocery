from models import LogBledow, PoziomLogu
from database import SessionLocal
import json

def log_to_db(poziom: PoziomLogu, modul: str, funkcja: str, komunikat: str, szczegoly: str = None):
    """Helper function to log to database"""
    with SessionLocal() as db:
        log = LogBledow(
            poziom=poziom,
            modul_aplikacji=modul,
            funkcja=funkcja,
            komunikat_bledu=komunikat,
            szczegoly_techniczne=szczegoly
        )
        db.add(log)
        db.commit()

@router.post("/uzytkownicy/", response_model=Uzytkownik)
async def create_user(
    user: UzytkownikCreate,
    db: Session = Depends(get_db)
):
    """Create a new user"""
    try:
        log_to_db(
            PoziomLogu.INFO,
            "routes.uzytkownicy",
            "create_user",
            "Tworzenie nowego użytkownika",
            json.dumps({
                "username": user.username,
                "email": user.email,
                "status": "started"
            })
        )
        
        db_user = Uzytkownik(
            username=user.username,
            email=user.email,
            hashed_password=get_password_hash(user.password)
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        
        log_to_db(
            PoziomLogu.INFO,
            "routes.uzytkownicy",
            "create_user",
            "Użytkownik utworzony pomyślnie",
            json.dumps({
                "user_id": db_user.id,
                "username": db_user.username,
                "email": db_user.email,
                "status": "completed"
            })
        )
        
        return db_user
        
    except Exception as e:
        log_to_db(
            PoziomLogu.ERROR,
            "routes.uzytkownicy",
            "create_user",
            "Błąd tworzenia użytkownika",
            json.dumps({
                "username": user.username,
                "email": user.email,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": str(e.__traceback__)
            })
        )
        raise

@router.get("/uzytkownicy/me", response_model=Uzytkownik)
async def read_users_me(
    current_user: Uzytkownik = Depends(get_current_user)
):
    """Get current user information"""
    try:
        log_to_db(
            PoziomLogu.INFO,
            "routes.uzytkownicy",
            "read_users_me",
            "Pobieranie informacji o bieżącym użytkowniku",
            json.dumps({
                "user_id": current_user.id,
                "username": current_user.username,
                "status": "started"
            })
        )
        
        log_to_db(
            PoziomLogu.INFO,
            "routes.uzytkownicy",
            "read_users_me",
            "Informacje o użytkowniku pobrane pomyślnie",
            json.dumps({
                "user_id": current_user.id,
                "username": current_user.username,
                "email": current_user.email,
                "status": "completed"
            })
        )
        
        return current_user
        
    except Exception as e:
        log_to_db(
            PoziomLogu.ERROR,
            "routes.uzytkownicy",
            "read_users_me",
            "Błąd pobierania informacji o użytkowniku",
            json.dumps({
                "user_id": current_user.id,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": str(e.__traceback__)
            })
        )
        raise

@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """Get access token for user"""
    try:
        log_to_db(
            PoziomLogu.INFO,
            "routes.uzytkownicy",
            "login_for_access_token",
            "Próba logowania użytkownika",
            json.dumps({
                "username": form_data.username,
                "status": "started"
            })
        )
        
        user = authenticate_user(db, form_data.username, form_data.password)
        if not user:
            log_to_db(
                PoziomLogu.ERROR,
                "routes.uzytkownicy",
                "login_for_access_token",
                "Nieprawidłowe dane logowania",
                json.dumps({
                    "username": form_data.username,
                    "error_type": "AuthenticationError"
                })
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        access_token = create_access_token(data={"sub": user.username})
        
        log_to_db(
            PoziomLogu.INFO,
            "routes.uzytkownicy",
            "login_for_access_token",
            "Użytkownik zalogowany pomyślnie",
            json.dumps({
                "user_id": user.id,
                "username": user.username,
                "status": "completed"
            })
        )
        
        return {"access_token": access_token, "token_type": "bearer"}
        
    except Exception as e:
        log_to_db(
            PoziomLogu.ERROR,
            "routes.uzytkownicy",
            "login_for_access_token",
            "Błąd logowania użytkownika",
            json.dumps({
                "username": form_data.username,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": str(e.__traceback__)
            })
        )
        raise 
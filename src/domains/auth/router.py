"""Authentication router with database integration."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.domains.auth.dependencies import CurrentUser
from src.domains.auth.schemas import (
    AppleLoginRequest,
    AuthResponse,
    GoogleLoginRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    ResendVerificationCodeRequest,
    SendVerificationCodeRequest,
    SocialAuthResponse,
    TokenResponse,
    UserResponse,
    VerifyCodeRequest,
    VerifyCodeResponse,
)
from src.domains.auth.service import AuthService

router = APIRouter()
security = HTTPBearer(auto_error=False)


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuthResponse:
    """Register a new user.

    Creates a new user account with default settings and returns
    authentication tokens.
    """
    auth_service = AuthService(db)

    # Check if user already exists
    existing_user = await auth_service.get_user_by_email(request.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este email já está cadastrado",
        )

    # Create user
    user = await auth_service.create_user(
        email=request.email,
        password=request.password,
        name=request.name,
        user_type=request.user_type,
    )

    # Generate tokens
    access_token, refresh_token = auth_service.generate_tokens(user.id)

    return AuthResponse(
        user=UserResponse.model_validate(user),
        tokens=TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
        ),
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    request: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuthResponse:
    """Authenticate user and return tokens.

    Validates credentials and returns access and refresh tokens.
    """
    auth_service = AuthService(db)

    # Authenticate user
    user = await auth_service.authenticate_user(
        email=request.email,
        password=request.password,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha inválidos",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sua conta está desativada",
        )

    # Generate tokens
    access_token, refresh_token = auth_service.generate_tokens(user.id)

    return AuthResponse(
        user=UserResponse.model_validate(user),
        tokens=TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
        ),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Refresh access token using refresh token.

    Validates the refresh token, blacklists it, and returns new tokens.
    """
    auth_service = AuthService(db)

    tokens = await auth_service.refresh_tokens(request.refresh_token)
    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    access_token, new_refresh_token = tokens

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: LogoutRequest,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Logout user by invalidating tokens.

    Blacklists both access and refresh tokens in Redis.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    auth_service = AuthService(db)
    await auth_service.logout(
        access_token=credentials.credentials,
        refresh_token=request.refresh_token,
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: CurrentUser,
) -> UserResponse:
    """Get current authenticated user information."""
    return UserResponse.model_validate(current_user)


@router.post("/google", response_model=SocialAuthResponse)
async def google_login(
    request: GoogleLoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SocialAuthResponse:
    """Authenticate or register user via Google Sign-In.

    Validates the Google ID token, creates a new user if needed,
    and returns authentication tokens.
    """
    auth_service = AuthService(db)

    result = await auth_service.authenticate_or_create_google_user(
        id_token=request.id_token,
    )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token do Google inválido ou expirado",
        )

    user, is_new_user = result

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sua conta está desativada",
        )

    # Generate tokens
    access_token, refresh_token = auth_service.generate_tokens(user.id)

    return SocialAuthResponse(
        user=UserResponse.model_validate(user),
        tokens=TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
        ),
        is_new_user=is_new_user,
    )


@router.post("/apple", response_model=SocialAuthResponse)
async def apple_login(
    request: AppleLoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SocialAuthResponse:
    """Authenticate or register user via Apple Sign-In.

    Validates the Apple ID token, creates a new user if needed,
    and returns authentication tokens.

    Note: Apple only provides the user's name on the first login.
    Pass user_name on first login to capture the user's name.
    """
    auth_service = AuthService(db)

    result = await auth_service.authenticate_or_create_apple_user(
        id_token=request.id_token,
        user_name=request.user_name,
    )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token da Apple inválido ou expirado",
        )

    user, is_new_user = result

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sua conta está desativada",
        )

    # Generate tokens
    access_token, refresh_token = auth_service.generate_tokens(user.id)

    return SocialAuthResponse(
        user=UserResponse.model_validate(user),
        tokens=TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
        ),
        is_new_user=is_new_user,
    )


@router.post("/send-verification", status_code=status.HTTP_200_OK)
async def send_verification_code(
    request: SendVerificationCodeRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Send a verification code to an email address.

    This endpoint can be used:
    - Before registration to verify the email
    - For existing unverified users to request a new code
    """
    auth_service = AuthService(db)

    # Check if user exists
    user = await auth_service.get_user_by_email(request.email)

    if user and user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este email já está verificado",
        )

    # Use the user's name if exists, otherwise use email prefix
    name = user.name if user else request.email.split("@")[0]

    # Send verification email
    sent = await auth_service.send_verification_email(
        email=request.email,
        name=name,
    )

    if not sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao enviar email de verificação",
        )

    return {"message": "Código de verificação enviado"}


@router.post("/verify-code", response_model=VerifyCodeResponse)
async def verify_email_code(
    request: VerifyCodeRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> VerifyCodeResponse:
    """Verify an email verification code.

    Returns whether the code was valid and marks the user's email as verified
    if they already have an account.
    """
    auth_service = AuthService(db)

    # Verify the code
    is_valid = await auth_service.verify_code(
        email=request.email,
        code=request.code,
        purpose="registration",
    )

    if not is_valid:
        return VerifyCodeResponse(
            verified=False,
            message="Código inválido ou expirado",
        )

    # If user exists, mark as verified
    user = await auth_service.get_user_by_email(request.email)
    if user:
        await auth_service.verify_user_email(user)

    return VerifyCodeResponse(
        verified=True,
        message="Email verificado com sucesso",
    )


@router.post("/resend-verification", status_code=status.HTTP_200_OK)
async def resend_verification_code(
    request: ResendVerificationCodeRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Resend verification code to an email address.

    Rate limited to prevent abuse.
    """
    auth_service = AuthService(db)

    # Check if user exists
    user = await auth_service.get_user_by_email(request.email)

    if user and user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este email já está verificado",
        )

    name = user.name if user else request.email.split("@")[0]

    # Send verification email
    sent = await auth_service.send_verification_email(
        email=request.email,
        name=name,
    )

    if not sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao enviar email de verificação",
        )

    return {"message": "Código de verificação reenviado"}

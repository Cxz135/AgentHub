# app/api/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from backend.app.dependencies import get_db
from backend.app.schemas import UserCreate, UserLogin, UserResponse, Token
from backend.models.user import User as UserModel
from backend.utils.logger import logger
import os
from dotenv import load_dotenv

load_dotenv()

# 配置
SECRET_KEY = os.getenv("JWT_SECRET", "your-secret-key-keep-it-safe")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30 * 24 * 60  # 30天

# 密码加密上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT认证方案
security = HTTPBearer()

router = APIRouter()

# 工具函数
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    """获取当前认证用户的依赖项"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user

# API端点
@router.post("/register", response_model=Token)
async def register(user_in: UserCreate, db: Session = Depends(get_db)):
    """用户注册"""
    # 检查用户名是否已存在
    existing_user = db.query(UserModel).filter(UserModel.username == user_in.username).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="用户名已存在")
    
    # 检查邮箱是否已存在
    existing_email = db.query(UserModel).filter(UserModel.email == user_in.email).first()
    if existing_email:
        raise HTTPException(status_code=409, detail="邮箱已被注册")
    
    # 创建新用户
    hashed_password = get_password_hash(user_in.password)
    db_user = UserModel(
        username=user_in.username,
        email=user_in.email,
        password_hash=hashed_password
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    # 生成访问令牌
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": db_user.id},
        expires_delta=access_token_expires
    )
    
    logger.info(f"✅ 新用户注册成功: {db_user.username}")
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/login", response_model=Token)
async def login(user_in: UserLogin, db: Session = Depends(get_db)):
    """用户登录"""
    # 查找用户
    user = db.query(UserModel).filter(UserModel.username == user_in.username).first()
    if not user or not verify_password(user_in.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(status_code=400, detail="账户已被禁用")
    
    # 生成访问令牌
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.id},
        expires_delta=access_token_expires
    )
    
    logger.info(f"✅ 用户登录成功: {user.username}")
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserResponse)
async def read_users_me(current_user: UserModel = Depends(get_current_user)):
    """获取当前用户信息"""
    return UserResponse.model_validate(current_user)
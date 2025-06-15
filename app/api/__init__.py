from flask import Blueprint

# 使用 url_prefix='/api' 為此藍圖中的所有路由自動加上 '/api' 前綴
bp = Blueprint('api', __name__, url_prefix='/api')

# 在檔案底部匯入路由，以避免循環相依性
from app.api import routes

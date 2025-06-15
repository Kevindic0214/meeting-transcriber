from flask import Blueprint

# template_folder='templates' 會在 'app/main/templates' 中尋找模板
# 我們希望使用 'app/templates'，這在註冊藍圖時是預設行為，所以這裡不用特別指定
bp = Blueprint('main', __name__)

# 在檔案底部匯入路由，以避免循環相依性
from app.main import routes

from app import create_app

# 透過應用程式工廠建立 app 實例
app = create_app()

if __name__ == "__main__":
    # 執行 app，並開啟 debug 模式
    # host='0.0.0.0' 讓外部網路可以存取
    app.run(debug=True, host='0.0.0.0', port=8080)

pyinstaller --onefile --noconsole --name "FinKat" ^
  --add-data "templates;templates" ^
  --add-data "static;static" ^
  --hidden-import cryptography ^
  --hidden-import requests ^
  --hidden-import flask ^
  --hidden-import flask_cors ^
  --hidden-import dotenv ^
  --hidden-import hwid ^
  app.py

pause
from src.app import app
import os

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    print(f'Botmaster license server running on http://localhost:{port}')
    print(f'  Download page: http://localhost:{port}/')
    print(f'  Admin dashboard: http://localhost:{port}/admin')
    app.run(host='0.0.0.0', port=port, debug=False)

from pathlib import Path


config = """server {
    listen 80;
    server_name catalystedgescanner.com www.catalystedgescanner.com 67.205.148.181;
    root /opt/catalyst/docs;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location ~ ^/(api|ws) {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
"""

Path("/etc/nginx/sites-available/cerebro").write_text(config, encoding="utf-8")
print("Nginx config written.")

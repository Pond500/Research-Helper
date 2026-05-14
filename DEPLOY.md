# Deploy Guide — Research Helper

## สถาปัตยกรรม Docker

```
Internet → port 10235 (Frontend: Next.js)
                ↓ internal Docker network
           agent:10236  (Python FastAPI + LangGraph)
                ↓
           qdrant:10237 (Vector DB)
```

เปิด firewall เฉพาะ **port 10235** เท่านั้น

---

## ขั้นตอนติดตั้งบน Server

### 1. ติดตั้ง Docker

```bash
# Ubuntu / Debian
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# ตรวจสอบ
docker --version
docker compose version
```

### 2. Clone โปรเจค

```bash
git clone https://github.com/Pond500/Research-Helper.git
cd Research-Helper
```

### 3. ตั้งค่า Environment Variables

```bash
cp .env.docker.example .env.docker
nano .env.docker
```

แก้ไขใส่ API keys จริง:

```env
# เลือกใช้อย่างใดอย่างหนึ่ง
OPENROUTER_API_KEY=sk-or-v1-...    # ถ้าใช้ OpenRouter
# OPENAI_API_KEY=sk-...            # ถ้าใช้ OpenAI โดยตรง

TAVILY_API_KEY=tvly-...
```

### 4. เปิด Firewall (Ubuntu/ufw)

```bash
sudo ufw allow 10235/tcp
sudo ufw reload
```

### 5. Start ระบบ

```bash
docker compose up -d --build
```

รอประมาณ 2-3 นาที (ครั้งแรก build image + download HuggingFace embedding model)

### 6. ตรวจสอบว่าทำงาน

```bash
# ดู status ทุก container
docker compose ps

# ดู log แบบ real-time
docker compose logs -f agent

# ทดสอบ health
curl http://localhost:10235
```

เปิดเบราว์เซอร์ไปที่ `http://<server-ip>:10235`

---

## ตั้งค่า Nginx Reverse Proxy (แนะนำ)

ถ้าต้องการใช้ domain name และ HTTPS ให้ติดตั้ง Nginx + Certbot:

```bash
sudo apt install nginx certbot python3-certbot-nginx -y
```

สร้าง config:

```bash
sudo nano /etc/nginx/sites-available/research-helper
```

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:10235;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_cache_bypass $http_upgrade;

        # SSE streaming — ปิด buffering เพื่อไม่ให้ stream ค้าง
        proxy_buffering off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/research-helper /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# ออก SSL certificate
sudo certbot --nginx -d your-domain.com
```

---

## คำสั่งที่ใช้บ่อย

```bash
# หยุดทั้งหมด
docker compose down

# Restart เฉพาะ agent (หลังแก้โค้ด Python)
docker compose up -d --build agent

# ดู log แบบ follow
docker compose logs -f

# ดู log เฉพาะ service
docker compose logs -f agent
docker compose logs -f frontend

# อัปเดตโค้ดจาก GitHub แล้ว redeploy
git pull
docker compose up -d --build
```

---

## อัปเดตโค้ดใหม่

```bash
# บน server
cd Research-Helper
git pull
docker compose up -d --build
```

---

## Ports สรุป

| Port | Service | เปิดออก internet? |
|---|---|---|
| 10235 | Next.js Frontend | ✅ ใช่ |
| 10236 | Python Agent | ❌ internal เท่านั้น |
| 10237 | Qdrant REST | ❌ internal เท่านั้น |
| 10238 | Qdrant gRPC | ❌ internal เท่านั้น |

---

## Troubleshooting

**Container ไม่ขึ้น:**
```bash
docker compose logs agent   # ดู error
docker compose ps           # ดู status
```

**Agent ไม่ตอบสนอง:**
```bash
# ตรวจ health
docker exec tako_agent python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:10236/health').read())"
```

**Qdrant ไม่ทำงาน (upload ไม่ได้):**
```bash
docker compose logs qdrant
docker compose restart qdrant
```

**ข้อมูล Qdrant หาย (หลัง restart):**
- ข้อมูลถูกเก็บใน Docker volume `tako-copilotkit_qdrant_data` ซึ่ง persist ข้าม restart อัตโนมัติ
- ถ้าทำ `docker compose down -v` จะลบ volume ด้วย — ระวัง!

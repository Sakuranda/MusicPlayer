#!/usr/bin/env bash
# 一键部署到 hk 服务器（需先完成 ssh hk 免密登录）
set -euo pipefail

REPO="https://github.com/Sakuranda/MusicPlayer.git"
DEPLOY_DIR="/opt/musicplayer"

echo "==> 同步代码到服务器…"
ssh hk "if [ -d $DEPLOY_DIR/.git ]; then git -C $DEPLOY_DIR pull --ff-only; else git clone $REPO $DEPLOY_DIR; fi"

echo "==> 准备配置（首次部署生成 API Token 与管理员账户）…"
ssh hk "bash -s" <<'EOF'
cd /opt/musicplayer
if [ ! -f deploy/.env ]; then
  cp deploy/.env.example deploy/.env
  TOKEN=$(openssl rand -hex 16)
  ADMIN_PASS=$(openssl rand -hex 12)
  AUTH_KEY=$(openssl rand -hex 32)
  sed -i "s/^API_TOKEN=$/API_TOKEN=$TOKEN/" deploy/.env
  sed -i "s/^ADMIN_USERNAME=$/ADMIN_USERNAME=admin/" deploy/.env
  sed -i "s/^ADMIN_PASSWORD=$/ADMIN_PASSWORD=$ADMIN_PASS/" deploy/.env
  sed -i "s/^AUTH_SECRET=$/AUTH_SECRET=$AUTH_KEY/" deploy/.env
  echo "已生成 deploy/.env（API_TOKEN=$TOKEN）"
  echo "网页登录账户：admin"
  echo "网页登录密码：$ADMIN_PASS（请立即妥善保存并修改）"
fi
EOF

echo "==> 构建并启动容器…"
ssh hk "cd $DEPLOY_DIR && docker compose up -d --build"

echo "==> 等待服务就绪…"
sleep 5
ssh hk "cd $DEPLOY_DIR && docker compose ps"

echo ""
echo "部署完成："
echo "  网页播放器: http://45.125.33.88:8080"
echo "  iOS (Navidrome/Amperfy): http://45.125.33.88:4533"

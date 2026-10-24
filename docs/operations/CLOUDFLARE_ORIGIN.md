# Cloudflare 回源安全部署

本文是 [`DEPLOYMENT.md`](DEPLOYMENT.md) 的 Cloudflare 场景补充，只覆盖“源站只接受 Cloudflare 回源”这一层：
UFW 白名单、Cloudflare 网段自动同步、Nginx 真实 IP 还原，以及应用侧的信任边界。

基础安装、systemd 应用服务、站点 Nginx 配置与 HTTPS 仍按 `DEPLOYMENT.md` 执行，本文不重复。

## 1. 目标与适用范围

部署完成后应达到以下效果：

- 源站 `80` / `443` 只允许 Cloudflare 官方网段访问，其他来源在 UFW 层直接丢弃
- Cloudflare 网段每 15 分钟自动同步，避免 Cloudflare 换段后源站被误拦
- Nginx 还原真实客户端 IP，应用限流、登录审计、评论审计不再记录 Cloudflare 边缘 IP
- 应用只信任本机 Nginx，不信任客户端伪造的 `X-Forwarded-For`
- 保留 SSH 管理通道，避免同步异常时无法登录服务器

适用环境：

- Debian 13 / Ubuntu 22.04+
- Nginx 1.24+，已包含 `http_realip_module`
- UFW + systemd
- 应用已按 `DEPLOYMENT.md` 监听 `127.0.0.1:8000`
- 域名已开启 Cloudflare 代理（橙云），SSL/TLS 模式建议 `Full (strict)`

> 注意：以下命令默认以 `root` 执行。启用 UFW 前必须先确认 SSH 规则已放行，
> 否则会把自己挡在服务器外。

## 2. 前置检查

```bash
nginx -V 2>&1 | grep -o with-http_realip_module
grep -n 'conf.d' /etc/nginx/nginx.conf
grep '^IPV6=' /etc/default/ufw
ss -tlnp | grep -E ':80|:443|:8000'
```

要求：

- 输出包含 `with-http_realip_module`
- `nginx.conf` 的 `http {}` 中包含：

  ```nginx
  include /etc/nginx/conf.d/*.conf;
  ```

- 源站有 IPv6 时，`/etc/default/ufw` 应为 `IPV6=yes`
- `80` / `443` 由 Nginx 监听，`8000` 只能监听 `127.0.0.1`，不能是 `0.0.0.0`

## 3. UFW 基础配置

先放行 SSH，再配置 Cloudflare 规则。不要提前执行 `ufw allow 80,443`。

```bash
apt-get update
apt-get install -y ufw nginx python3

ufw default deny incoming
ufw default allow outgoing

# 建议只允许管理 IP，而不是 Anywhere
ufw allow from <ADMIN_IP> to any port <SSH_PORT> proto tcp comment 'ssh-admin'
```

如果 UFW 之前已经全局放行了 `80` / `443`，先删除：

```bash
ufw status numbered
ufw --force delete <规则编号>
```

删除多条规则时从编号大的往小的删，避免删除后编号整体前移。

此时先不要执行 `ufw enable`，等 Cloudflare 规则写入后再启用。

## 4. 安装 Cloudflare 网段同步脚本

脚本职责：

- 从 Cloudflare 官方 API 获取 IPv4 / IPv6 网段
- 更新 `/etc/cloudflare/ips.txt`
- 自动增删带 `cf-origin` 注释的 UFW 规则
- 自动生成 Nginx `real_ip` 配置
- 配置变化时执行 `nginx -t` 并 reload
- Nginx 校验失败时恢复旧配置

创建脚本：

```bash
cat >/usr/local/sbin/cloudflare-ufw-sync <<'PY'
#!/usr/bin/env python3
"""同步 Cloudflare 官方回源网段到 UFW 与 Nginx real_ip 配置。"""

import ipaddress
import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

API = "https://api.cloudflare.com/client/v4/ips"
PORTS = (80, 443)
MARKER = "cf-origin"
STATE = Path("/etc/cloudflare/ips.txt")
NGINX_CONF = Path("/etc/nginx/conf.d/cloudflare-real-ip.conf")


def run(args):
    # 固定英文环境，避免本地化后的 ufw 输出导致规则解析失败
    environment = {**os.environ, "LC_ALL": "C"}
    return subprocess.run(
        args,
        check=True,
        text=True,
        capture_output=True,
        env=environment,
    )


def fetch_networks():
    request = urllib.request.Request(
        API,
        headers={"User-Agent": "rewrz-cf-origin-sync/1.0"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.load(response)

    if not payload.get("success"):
        raise RuntimeError("Cloudflare API 返回 success=false")

    result = payload.get("result") or {}
    networks = []

    for key in ("ipv4_cidrs", "ipv6_cidrs"):
        for value in result.get(key, []):
            network = ipaddress.ip_network(value, strict=True)
            if not network.is_global:
                raise ValueError(f"非全局网段：{network}")
            networks.append(network)

    ipv4 = [n for n in networks if n.version == 4]
    ipv6 = [n for n in networks if n.version == 6]

    # 数量下限用于识别 API 返回结构变化，避免把空列表当成有效结果
    if len(ipv4) < 10 or len(ipv6) < 5:
        raise ValueError(f"网段数量异常：v4={len(ipv4)} v6={len(ipv6)}")

    return sorted(
        set(networks),
        key=lambda n: (n.version, int(n.network_address), n.prefixlen),
    )


def current_rules():
    output = run(["ufw", "status", "numbered"]).stdout
    pattern = re.compile(
        r"^\s*\[\s*(\d+)\]\s+(\d+)/tcp(?:\s+\(v6\))?\s+ALLOW IN\s+(\S+)(?:\s+#\s*(.*))?\s*$"
    )
    rules = []

    for line in output.splitlines():
        match = pattern.match(line)
        if not match:
            continue

        number, port, source, comment = match.groups()
        if not comment or not comment.strip().startswith(MARKER):
            continue

        try:
            network = ipaddress.ip_network(source, strict=False)
        except ValueError:
            continue

        rules.append((int(number), int(port), network))

    return rules


def add_rule(port, network):
    run([
        "ufw", "allow",
        "from", str(network),
        "to", "any",
        "port", str(port),
        "proto", "tcp",
        "comment", MARKER,
    ])


def delete_rules(pairs):
    rules = current_rules()
    numbers = sorted(
        {
            number
            for number, port, network in rules
            if (port, network) in pairs
        },
        reverse=True,
    )
    for number in numbers:
        run(["ufw", "--force", "delete", str(number)])


def write_nginx_real_ip(networks):
    lines = [
        "# 由 cloudflare-ufw-sync 依据 Cloudflare API 生成，请勿手工编辑。",
        *(f"set_real_ip_from {network};" for network in networks),
        "real_ip_header CF-Connecting-IP;",
        "real_ip_recursive on;",
    ]
    content = "\n".join(lines) + "\n"

    try:
        previous = NGINX_CONF.read_text(encoding="utf-8")
    except FileNotFoundError:
        previous = None

    if previous == content:
        return False

    NGINX_CONF.parent.mkdir(parents=True, exist_ok=True)
    temporary = NGINX_CONF.with_suffix(".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.chmod(0o644)
    os.replace(temporary, NGINX_CONF)

    try:
        run(["nginx", "-t"])
    except Exception:
        if previous is None:
            NGINX_CONF.unlink(missing_ok=True)
        else:
            NGINX_CONF.write_text(previous, encoding="utf-8")
        raise

    run(["systemctl", "reload", "nginx"])
    return True


def main():
    desired = fetch_networks()
    current = current_rules()

    desired_pairs = {
        (port, network)
        for network in desired
        for port in PORTS
    }
    current_pairs = {
        (port, network)
        for _, port, network in current
    }

    to_add = sorted(
        desired_pairs - current_pairs,
        key=lambda item: (
            item[0],
            item[1].version,
            int(item[1].network_address),
            item[1].prefixlen,
        ),
    )
    to_remove = current_pairs - desired_pairs

    for port, network in to_add:
        add_rule(port, network)

    if to_add:
        print(f"已新增 {len(to_add)} 条规则", flush=True)

    if to_remove:
        delete_rules(to_remove)
        print(f"已删除 {len(to_remove)} 条规则", flush=True)

    if not to_add and not to_remove:
        print("无需变更", flush=True)

    STATE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(
        "\n".join(str(network) for network in desired) + "\n",
        encoding="utf-8",
    )
    temporary.chmod(0o644)
    os.replace(temporary, STATE)

    if write_nginx_real_ip(desired):
        print("已更新 Nginx real_ip 配置", flush=True)


if __name__ == "__main__":
    main()
PY

chmod 755 /usr/local/sbin/cloudflare-ufw-sync
```

## 5. 安装 systemd service 与 timer

```bash
cat >/etc/systemd/system/cloudflare-ufw-sync.service <<'EOF'
[Unit]
Description=同步 Cloudflare 回源网段到 UFW 与 Nginx
After=network-online.target ufw.service nginx.service
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/cloudflare-ufw-sync
EOF

cat >/etc/systemd/system/cloudflare-ufw-sync.timer <<'EOF'
[Unit]
Description=定时同步 Cloudflare 回源网段

[Timer]
OnCalendar=*:0/15
Persistent=true
RandomizedDelaySec=60

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
```

## 6. 首次同步并启用 UFW

先手动运行一次，让 Cloudflare 规则和 Nginx 配置生成：

```bash
/usr/local/sbin/cloudflare-ufw-sync
```

检查 UFW：

```bash
ufw status numbered
```

应能看到大量类似规则：

```text
80/tcp   ALLOW IN   104.16.0.0/13   # cf-origin
443/tcp  ALLOW IN   104.16.0.0/13   # cf-origin
```

确认 SSH 规则存在后，再启用 UFW：

```bash
ufw --force enable
ufw status verbose
```

启用定时同步：

```bash
systemctl enable --now cloudflare-ufw-sync.timer
systemctl list-timers cloudflare-ufw-sync.timer --no-pager
```

## 7. Nginx 还原真实客户端 IP

同步脚本会生成 `/etc/nginx/conf.d/cloudflare-real-ip.conf`，内容示例：

```nginx
# 由 cloudflare-ufw-sync 依据 Cloudflare API 生成，请勿手工编辑。
set_real_ip_from 103.21.244.0/22;
set_real_ip_from 103.22.200.0/22;
...
real_ip_header CF-Connecting-IP;
real_ip_recursive on;
```

该文件由 `nginx.conf` 的 `http {}` 引入。如果站点配置中已经按 `DEPLOYMENT.md`
手写过 `set_real_ip_from` / `real_ip_header`，请删除手写部分，统一由生成文件维护，
避免两套网段并存。

站点配置中的关键点是 `X-Forwarded-For` 使用 `$remote_addr`：

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;

    proxy_set_header Host $http_host;
    proxy_set_header X-Real-IP $remote_addr;
    # 必须覆盖，不能追加；$remote_addr 已被 real_ip 还原为真实客户端
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

不要使用：

```nginx
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
```

原因：

- `real_ip` 已把 `$remote_addr` 还原为真实客户端
- 追加模式会保留客户端可伪造的 `X-Forwarded-For` 链；应用侧部分审计逻辑取 XFF 首段，
  会把伪造值记录下来
- 应用层再做 IP 限流 / 审计时容易再次取到错误 IP

校验并 reload：

```bash
nginx -t
systemctl reload nginx
```

确认配置已加载：

```bash
nginx -T | grep -E 'real_ip_header|set_real_ip_from' | head
```

## 8. 应用侧配置

`.env` 中只需要保留本机代理：

```env
ALLOWED_HOSTS=example.com,www.example.com,127.0.0.1,localhost
SITE_URL=https://example.com
TRUSTED_PROXIES=127.0.0.1,::1
```

说明：

- `ALLOWED_HOSTS` 中的 `127.0.0.1` 用于保留 `update.sh` 的本机健康检查
- `TRUSTED_PROXIES` 保持默认即可，不要把 Cloudflare 网段加进去：
  Nginx 已经完成真实 IP 还原，应用看到的直连方始终是本机 Nginx
- 应用按 `TRUSTED_PROXIES` 判断直连方是否可信，再从右向左解析 `X-Forwarded-For`，
  客户端伪造的左侧条目不会生效
- 后台访问统计的 UV 去重与页面浏览上报限流（单 IP 每分钟 120 条）依赖真实 IP；
  Nginx 已还原真实 IP 时保持 `TRUSTED_PROXIES=127.0.0.1,::1` 即可，
  只有在 CDN / 反代直接回源、应用前没有 Nginx 还原时才需要写入回源网段
- 修改 `.env` 后需要重启应用服务：`systemctl restart rewrz`

systemd 的 `ExecStart` 不需要为 Cloudflare 增加 `--proxy-headers`。
如果自行添加，必须限定 `--forwarded-allow-ips=127.0.0.1`，不要使用 `*`。

## 9. 验收

### 9.1 公网访问

```bash
curl -I https://example.com/
```

应返回 `200` 或正常业务状态。

### 9.2 真实 IP

用外部客户端访问后查看 Nginx 访问日志：

```bash
tail -n 20 /var/log/nginx/access.log
```

应看到访问者公网 IP，而不是 Cloudflare 边缘 IP（如 `104.x`、`172.6x`、`162.158.x`）。

应用侧到后台“登录审计”或评论记录中确认 IP 为真实客户端地址。
Uvicorn 默认访问日志中的客户端地址可能仍是 `127.0.0.1`（未启用 `--proxy-headers` 时的正常现象），
判断真实 IP 以 Nginx 访问日志与后台审计记录为准。

### 9.3 同步幂等性

```bash
systemctl start cloudflare-ufw-sync.service
journalctl -u cloudflare-ufw-sync -n 20 --no-pager
```

第二次运行通常应看到：

```text
无需变更
```

如果 Cloudflare 网段有变化，会看到：

```text
已新增 N 条规则
已删除 N 条规则
已更新 Nginx real_ip 配置
```

### 9.4 非 Cloudflare 直连

从非 Cloudflare 网络直接访问源站 IP：

```bash
curl --connect-timeout 5 http://<ORIGIN_IP>/
```

应连接失败或超时。不要从源站本机测试，本机回环流量不受 UFW 入站规则影响。

### 9.5 防止伪造 CF 头

不要配置：

```nginx
set_real_ip_from 0.0.0.0/0;
```

否则任何能直连源站的人都可以伪造 `CF-Connecting-IP`。只允许 Cloudflare 官方网段。

### 9.6 访问统计上报

公开页会向 `POST /api/v1/traffic/pageview` 发送页面浏览上报（sendBeacon），
用于补全命中 Cloudflare 缓存、未回源的访问。确认该端点可直接回源：

```bash
curl -i -X POST https://example.com/api/v1/traffic/pageview \
  -H 'Content-Type: application/json' \
  -H 'Origin: https://example.com' \
  -H 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36' \
  -d '{"path":"/","referrer":"","query":""}'
```

`URL` 与 `Origin` 要替换为实际站点域名；`curl` 默认 UA 会被当作机器人而忽略，
因此必须带一个正常浏览器 UA 才能验证计数增长。

应返回 `204 No Content`，并带 `Cache-Control: no-store`。
若返回 403/404/5xx 或空响应，检查 WAF 规则、缓存规则与应用路由；
后台“访问统计”页的“上报”计数会在 15–45 秒内增加。

DNT 用户、禁用 JS 的用户与爬虫不会执行上报，这部分由回源 PV 兜底。

## 10. 日常维护

查看同步状态：

```bash
systemctl list-timers cloudflare-ufw-sync.timer --no-pager
journalctl -u cloudflare-ufw-sync -n 50 --no-pager
```

查看 UFW：

```bash
ufw status numbered
```

查看当前缓存的 Cloudflare 网段：

```bash
cat /etc/cloudflare/ips.txt
```

当前官方列表通常是 15 个 IPv4 + 7 个 IPv6，对应约 44 条 UFW 规则（22 个网段 × `80`/`443`）。
数量不必硬编码，以脚本校验结果为准。

`cf-origin` 规则由脚本统一管理：手工删除的规则会在下次同步时补回；
手工新增但不带 `cf-origin` 注释的规则不会被脚本清理，排查时注意区分。

## 11. 故障处理

### 11.1 站点突然 521 / 522

优先检查：

```bash
ufw status verbose
systemctl status nginx --no-pager
systemctl status rewrz --no-pager
journalctl -u cloudflare-ufw-sync -n 50 --no-pager
```

常见原因：

- Cloudflare 新网段尚未同步
- UFW 规则被误删
- Nginx 或应用未启动
- 源站只监听了 IPv4，但 Cloudflare 走了 IPv6

### 11.2 真实 IP 仍是 Cloudflare 边缘 IP

检查：

```bash
nginx -T | grep real_ip
tail -n 20 /var/log/nginx/access.log
```

确认：

- Cloudflare 代理已开启（橙云）
- 请求确实带 `CF-Connecting-IP`
- `cloudflare-real-ip.conf` 被 `http {}` 加载
- Nginx 已 reload
- 站点配置的 `X-Forwarded-For` 已改为 `$remote_addr`

### 11.3 同步失败

```bash
journalctl -u cloudflare-ufw-sync -n 100 --no-pager
/usr/local/sbin/cloudflare-ufw-sync
```

脚本在拉取 Cloudflare API 失败时会直接退出，不会先清空现有规则。
保持 SSH 可用；必要时通过服务商控制台登录后临时执行：

```bash
ufw disable
```

处理完再重新启用。

### 11.4 Nginx 配置校验失败

脚本会自动恢复上一版 `cloudflare-real-ip.conf`，但仍需手动检查：

```bash
nginx -t
journalctl -u cloudflare-ufw-sync -n 100 --no-pager
```

### 11.5 服务器上还有 Docker

Docker 会自行插入 `DOCKER` 链，绕过 UFW 的端口规则。若同时运行 Docker，
需要单独限制容器端口映射，不能只依赖本文的 UFW 规则。

## 12. 回滚

```bash
systemctl disable --now cloudflare-ufw-sync.timer

rm -f /etc/nginx/conf.d/cloudflare-real-ip.conf

# 恢复站点配置中的 X-Forwarded-For 后：
nginx -t
systemctl reload nginx

# 删除 cf-origin 规则（从编号大的往小的删）
ufw status numbered
ufw --force delete <编号>

# 如需恢复公网直连：
ufw allow 80,443/tcp
```

如果只是临时恢复访问：

```bash
ufw disable
```

## 13. 安全边界

Cloudflare IP 白名单不是身份认证。其他 Cloudflare 用户也可能通过 Cloudflare 访问源站，因此仍需：

- 严格 Host 校验（`ALLOWED_HOSTS`）
- 应用登录鉴权
- WAF / 速率限制
- 不暴露管理后台到公网

建议进一步启用 Cloudflare Authenticated Origin Pulls（mTLS）：
IP 白名单只能限制网络来源，mTLS 才能证明请求确实来自你的 Cloudflare 账户。

其他约束：

- SSH 不要走 Cloudflare，建议只允许管理 IP 或 Tailscale / WireGuard
- 应用端口只监听 `127.0.0.1:8000`，不要监听 `0.0.0.0:8000`
- 不要信任客户端 `X-Forwarded-For`：Nginx 必须覆盖，应用只信任本机 Nginx
- Cloudflare 换段时存在最长约 15 分钟同步窗口；对可用性要求更高可缩短周期，
  但要考虑 API 频率与 UFW 变更成本

## 14. 参考验证环境

本文流程已在 Debian 13 + Nginx 1.26.3 + UFW 环境验证：

- UFW 仅保留 Cloudflare 网段的 `80` / `443` 入站
- `cloudflare-ufw-sync` 每 15 分钟运行，正常时输出 `无需变更`
- Cloudflare 网段变化时自动增删 UFW 规则
- Nginx `real_ip` 配置自动生成并 reload
- Nginx 访问日志与后台审计记录为真实客户端 IP，而非 Cloudflare 边缘 IP
- `nginx -t` 通过，站点公网访问正常

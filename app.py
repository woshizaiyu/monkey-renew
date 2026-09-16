#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Monkey-Network 自动续期 (dash.monkey-network.xyz)
基于 eooce/Auto-Renew-Bothosting 骨架改造 + Lunes 邮箱密码登录块.
目标: 单账号单服 MVP, 邮箱+密码登录 -> Lifecycle Tab -> Confirm Server.
"""

import os
import re
import sys
import time
import requests
from datetime import datetime
from seleniumbase import SB

BASE = "https://dash.monkey-network.xyz"

# ---- Secrets ( Actions 里配置, 也可私库直接填双引号内 ) ----
MONKEY_EMAIL = os.environ.get("MONKEY_EMAIL") or ""
MONKEY_PASSWORD = os.environ.get("MONKEY_PASSWORD") or ""
# 单服 MVP 可留空(自动点第一台); 若有多服/定位不准, 手动填 server 短 id 或完整 uuid
MONKEY_SERVER_ID = os.environ.get("MONKEY_SERVER_ID") or ""
TG_CHAT_ID = os.environ.get("TG_CHAT_ID") or ""
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN") or ""
# 官方 Client API Key(可选, 仅用于续期前查询状态, 无 confirm 端点所以不能替代浏览器)
MONKEY_API_KEY = os.environ.get("MONKEY_API_KEY") or ""

if not MONKEY_EMAIL or not MONKEY_PASSWORD:
    print("ℹ️ 未配置 MONKEY_EMAIL / MONKEY_PASSWORD, 脚本终止。")
    sys.exit(1)


# ---------- Telegram ----------
def send_tg(text: str):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("⚠️ Telegram 未配置, 跳过通知")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT_ID, "text": text},
            timeout=10,
        )
        print("✅ Telegram 通知已发送")
    except Exception as e:
        print(f"❌ Telegram 发送失败: {e}")


def mask_email(email: str) -> str:
    if "@" in email:
        name, domain = email.split("@", 1)
        if len(name) > 4:
            return f"{name[:2]}****{name[-2:]}@{domain}"
        return f"{name}@{domain}"
    return email[:2] + "****"


def notify(status: str, extra: str = "", error: str = "") -> str:
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 8 * 3600))
    lines = [
        "🐵 Monkey-Network 续期通知",
        "",
        status,
        f"👤 账号: {mask_email(MONKEY_EMAIL)}",
    ]
    if extra:
        lines.append(extra)
    if error:
        lines.append(f"⚠️ 错误: {error}")
    lines.append(f"⏱️ 时间: {now}(UTC+8)")
    msg = "\n".join(lines)
    print(msg)
    send_tg(msg)
    return msg


# ---------- Turnstile / CF ----------
def wait_for_turnstile_pass(sb, timeout=25) -> bool:
    start = time.time()
    cf_indicators = ["verify you are human", "确认您是真人", "请验证您是真人",
                     "请确认您是真人", "正在进行安全验证", "just a moment",
                     "attention required", "verifying", "security verification",
                     "performing security verification",
                     "challenges.cloudflare.com", "cf-turnstile"]
    while time.time() - start < timeout:
        try:
            page_lower = (sb.get_page_source() or "").lower()
        except Exception:
            return True
        if not any(x in page_lower for x in cf_indicators):
            print("✅ CF/Turnstile 已通过")
            return True
        sb.sleep(1)
    print("❌ CF/Turnstile 验证超时")
    return False


def try_click_turnstile(sb, rounds=3) -> None:
    for i in range(1, rounds + 1):
        try:
            sb.uc_gui_click_captcha()
            print(f"🖱️ 第 {i} 次尝试点击 Turnstile")
            time.sleep(10)
        except Exception as e:
            print(f"⚠️ 点击 Turnstile 出错: {e}")
        if wait_for_turnstile_pass(sb, timeout=15):
            return


# ---------- React 表单填充 (抄 Lunes, 对受控组件有效) ----------
def js_fill_input(sb, selector: str, text: str):
    safe = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "")
    sb.execute_script(
        f"""
    (function(){{
        var el = document.querySelector('{selector}');
        if (!el) return;
        el.focus();
        var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value");
        if (setter && setter.set) setter.set.call(el, "{safe}");
        else el.value = "{safe}";
        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
    }})()
    """
    )


def get_current_ip(proxy_server: str = "") -> str:
    proxies = {"http": proxy_server, "https": proxy_server} if proxy_server else None
    r = requests.get("https://api.ip.sb/ip", proxies=proxies, timeout=15)
    r.raise_for_status()
    return r.text.strip()


# ---------- 官方 API 状态查询 (可选增强, 失败不阻塞) ----------
def query_api_status():
    if not MONKEY_API_KEY:
        return
    try:
        r = requests.get(
            f"{BASE}/api/client",
            headers={"Authorization": f"Bearer {MONKEY_API_KEY}", "Accept": "application/json"},
            timeout=15,
        )
        print(f"🔎 Client API 状态: HTTP {r.status_code} (仅查询, 无 confirm 端点)")
    except Exception as e:
        print(f"⚠️ Client API 查询失败(忽略): {e}")


# ---------- 登录 ----------
def login(sb) -> bool:
    print(f"🌐 打开登录页: {BASE}")
    sb.uc_open_with_reconnect(BASE, reconnect_time=5)
    time.sleep(5)
    if not wait_for_turnstile_pass(sb, timeout=20):
        print("🔒 检测到 CF 整页盾，尝试点击验证框 ...")
        try_click_turnstile(sb, rounds=5)
        if not wait_for_turnstile_pass(sb, timeout=20):
            print(f"❌ CF 盾未过，当前 URL: {sb.get_current_url()}")
            sb.save_screenshot("cf_blocked.png")
            return False

    # 找邮箱/密码框 (多选择器兜底, Monkey 用 email+password 老式表单)
    email_sel = password_sel = ""
    for sel in ['input[name="email"]', 'input[name="Email"]', 'input[type="email"]',
                'input[name="username"]', 'input[name="user"]']:
        try:
            if sb.is_element_visible(sel):
                email_sel = sel
                break
        except Exception:
            pass
    for sel in ['input[name="password"]', 'input[name="Password"]', 'input[type="password"]']:
        try:
            if sb.is_element_visible(sel):
                password_sel = sel
                break
        except Exception:
            pass
    if not email_sel or not password_sel:
        print(f"❌ 未找到登录表单, 当前 URL: {sb.get_current_url()}")
        sb.save_screenshot("login_no_form.png")
        return False

    print(f"📧 填写账号 ({email_sel}) ...")
    js_fill_input(sb, email_sel, MONKEY_EMAIL)
    time.sleep(0.5)
    print("🔑 填写密码 ...")
    js_fill_input(sb, password_sel, MONKEY_PASSWORD)
    time.sleep(1)

    # 登录框内也可能嵌 Turnstile
    try:
        exists = sb.execute_script(
            "return document.querySelector('input[name=\"cf-turnstile-response\"]') !== null")
    except Exception:
        exists = False
    if exists:
        print("🔒 登录框检测到 Turnstile, 尝试点击 ...")
        try_click_turnstile(sb)

    print("🖱️ 提交登录 ...")
    clicked = False
    for sel in ['button[type="submit"]', 'button:contains("Sign In")', 'button:contains("登录")',
                'button:contains("Log in")']:
        try:
            sb.click(sel, timeout=5)
            clicked = True
            break
        except Exception:
            pass
    if not clicked:
        try:
            sb.execute_script("document.querySelector('form').submit()")
        except Exception:
            pass
    time.sleep(4)

    # 登录成功判定: URL 脱离 /auth, 或出现 server/dashboard/lifecycle/server-card 关键字
    for _ in range(15):
        try:
            url = sb.get_current_url() or ""
            src = (sb.get_page_source() or "").lower()
        except Exception:
            time.sleep(1)
            continue
        if "/auth" not in url and ("lifecycle" in src or "server" in src or "dashboard" in src
                                   or "confirm" in src or "logout" in src):
            print(f"✅ 登录成功, 当前: {url}")
            return True
        if "/auth" not in url and "sign in" not in src[:2000]:
            print(f"✅ 登录成功(宽松判定), 当前: {url}")
            return True
        time.sleep(1)
    print(f"❌ 登录失败, 停留在: {sb.get_current_url()}")
    sb.save_screenshot("login_failed.png")
    return False


# ---------- 进服务器 -> Lifecycle ----------
def goto_lifecycle(sb) -> bool:
    """进入 Lifecycle Tab. 成功返回 True (无论按钮是否可点)."""
    # 方式0: 用户给了 SERVER_ID, 直试常见路由
    if MONKEY_SERVER_ID:
        for path in [f"/server/{MONKEY_SERVER_ID}/lifecycle", f"/server/{MONKEY_SERVER_ID}",
                     f"/servers/{MONKEY_SERVER_ID}"]:
            try:
                sb.open(BASE + path)
                sb.sleep(3)
                src = (sb.get_page_source() or "").lower()
                if "lifecycle" in src or "confirm" in src:
                    print(f"✅ 直达 Lifecycle: {path}")
                    return True
            except Exception:
                pass
    # 方式1: 点第一台 server 卡片
    try:
        sb.open(BASE)
        sb.sleep(4)
    except Exception:
        pass
    try:
        cards = sb.find_elements('a[href*="server"]')
    except Exception:
        cards = []
    if MONKEY_SERVER_ID:
        # 在卡片中优先找 id 匹配的
        for c in cards:
            try:
                if MONKEY_SERVER_ID in (c.get_attribute("href") or ""):
                    print(f"🖱️ 点击指定服务器: {MONKEY_SERVER_ID}")
                    c.click()
                    sb.sleep(4)
                    break
            except Exception:
                pass
    elif cards:
        try:
            href = cards[0].get_attribute("href")
            print(f"🖱️ 点击第一台服务器: {href}")
            cards[0].click()
            sb.sleep(4)
        except Exception as e:
            print(f"⚠️ 点击卡片失败: {e}")
    # 方式2: 找 Lifecycle Tab 并点击
    for sel in ['a:contains("Lifecycle")', 'button:contains("Lifecycle")',
                '[data-tab="lifecycle"]', 'a[href*="lifecycle"]']:
        try:
            if sb.is_element_visible(sel):
                print(f"🖱️ 点击 Lifecycle Tab ({sel})")
                sb.click(sel)
                sb.sleep(3)
                break
        except Exception:
            pass
    try:
        src = (sb.get_page_source() or "").lower()
    except Exception:
        return False
    if "lifecycle" in src or "confirm" in src:
        print("✅ 已到达 Lifecycle 页面")
        return True
    print("⚠️ 未确认到达 Lifecycle, 继续尝试解析页面 ...")
    return True  # 让后续解析再判定, 不直接判死


def parse_remaining(src_lower: str) -> str:
    """从页面提取剩余时间, 找不到返回空."""
    pats = [
        r"(\d+\s*days?\s*\d*\s*hours?\s*\d*\s*min?)",
        r"(\d+\s*days?\s*\d*\s*hours?)",
        r"(\d+\s*d\s*\d*\s*h)",
        r"(\d{1,3}:\d{2}:\d{2})",
        r"remaining\D{0,20}(\d+[^<]{0,40})",
    ]
    for p in pats:
        m = re.search(p, src_lower)
        if m:
            return m.group(1).strip()[:60]
    return ""


def do_renew(sb) -> None:
    goto_lifecycle(sb)
    sb.sleep(2)
    try:
        src = sb.get_page_source() or ""
    except Exception as e:
        notify("❌ 续期失败", error=f"无法读取 Lifecycle 页面: {e}")
        return
    src_lower = src.lower()
    remaining = parse_remaining(src_lower)
    if remaining:
        print(f"⏳ 当前剩余: {remaining}")

    # 找 Confirm 按钮 (多文案兜底)
    confirm_sel = ""
    for sel in ['button:contains("Confirm Server")', 'button:contains("Confirm")',
                'button:contains("确认")', 'button:contains("Renew")', 'button:contains("Extend")']:
        try:
            if sb.is_element_visible(sel):
                confirm_sel = sel
                print(f"✅ 找到确认按钮: '{sb.get_text(sel).strip()[:80]}' ({sel})")
                break
        except Exception:
            pass
    if not confirm_sel:
        # 可能还没到可点时间 (amber 7天 窗口) 或选择器漂移
        if remaining:
            notify("⏳ 未到续期时间或按钮未激活", extra=f"⏱️ 剩余: {remaining}\n(按钮仅剩≤7天可点, 到期前每3天会再试)")
        else:
            sb.save_screenshot("lifecycle_unknown.png")
            notify("ℹ️ 未找到确认按钮", error="页面结构可能变化, 请手动检查 Lifecycle 页 (已截图)")
        return

    # 检查 disabled
    try:
        disabled = sb.execute_script(
            f"var el=document.evaluate(\"//button[contains(.,'Confirm') or contains(.,'Renew')]\","
            "document,null,9,null).singleNodeValue; return el ? (el.disabled || "
            "el.getAttribute('aria-disabled')) : 'no-el'")
        print(f"🔎 按钮 disabled 状态: {disabled}")
        if disabled is True or disabled == "true":
            notify("⏳ 未到续期时间", extra=f"⏱️ 剩余: {remaining or '未知'}\n(确认按钮置灰, ≤7天 amber 区才可点)")
            return
    except Exception:
        pass

    print("🔄 点击确认按钮 ...")
    try:
        sb.click(confirm_sel)
        sb.sleep(8)
    except Exception as e:
        sb.save_screenshot("confirm_click_fail.png")
        notify("❌ 续期失败", error=f"点击确认按钮出错: {e}")
        return

    # 二次确认弹窗 (如果有)
    for sel in ['button:contains("Confirm")', 'button:contains("Yes")', 'button:contains("确认")']:
        try:
            if sb.is_element_visible(sel):
                print(f"🖱️ 点击二次确认 ({sel})")
                sb.click(sel)
                sb.sleep(5)
                break
        except Exception:
            pass

    try:
        new_src = (sb.get_page_source() or "").lower()
    except Exception as e:
        notify("⚠️ 续期结果未知", error=f"点击后页面读取失败: {e}")
        return
    new_remaining = parse_remaining(new_src)
    if "14 day" in new_src or "14-day" in new_src or "14days" in new_src.replace(" ", ""):
        notify("✅ 续期成功", extra=f"⏱️ 计时器已重置为 14 天\n剩余: {new_remaining or '已重置'}")
    elif new_remaining and new_remaining != remaining:
        notify("✅ 续期成功(计时器已变化)", extra=f"⏱️ 之前: {remaining or '未知'}\n现在: {new_remaining}")
    elif "confirm" not in new_src and remaining:
        notify("✅ 可能已续期(按钮消失)", extra=f"⏱️ 之前剩余: {remaining}\n请下次运行确认")
    else:
        sb.save_screenshot("renew_unknown.png")
        notify("⚠️ 续期结果未知", extra=f"⏱️ 点击前剩余: {remaining or '未知'}\n请登录后台人工确认")


def main():
    print("#" * 25)
    print("   Monkey-Network 自动续期")
    print("#" * 25)
    IS_PROXY = os.environ.get("IS_PROXY", "false").lower() == "true"
    PROXY_SERVER = os.environ.get("PROXY_SERVER", "").strip() or "http://127.0.0.1:1080"
    sb_kwargs = {"uc": True, "headless": False}
    if IS_PROXY:
        print(f"🔗 挂载代理: {PROXY_SERVER}")
        sb_kwargs["proxy"] = PROXY_SERVER
    else:
        print("🍭 未使用代理, 直连访问")

    with SB(**sb_kwargs) as sb:
        try:
            ip = get_current_ip(PROXY_SERVER if IS_PROXY else "")
            print(f"📍 当前出口IP: {ip}")
        except Exception as e:
            print(f"⚠️ 获取出口 IP 失败: {e}")
        query_api_status()
        print("🚀 启动浏览器 ...")
        if not login(sb):
            notify("❌ 登录失败", error="邮箱/密码错误或 CF 盾未过, 请检查 Secrets 与代理")
            return
        do_renew(sb)
        print("🏁 脚本执行完毕")


if __name__ == "__main__":
    main()

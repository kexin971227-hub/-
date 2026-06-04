import json
import os
import requests
from datetime import datetime, timedelta, timezone
import time
import threading
import logging
import re

# ========== 日志配置 ==========
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

log_filename = os.path.join(LOG_DIR, f"bot_{datetime.now().strftime('%Y-%m-%d')}.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def log_print(msg, level="info"):
    if level == "info":
        logger.info(msg)
    elif level == "error":
        logger.error(msg)
    elif level == "warning":
        logger.warning(msg)
    print(msg)

# ========== 北京时间 UTC+8 ==========
BEIJING_TZ = timezone(timedelta(hours=8))

def beijing_now():
    return datetime.now(BEIJING_TZ)

BOT_TOKEN = "13243514:3DFu4gK87ZWCPu4nWdLWY21Q4mZy2DgZZBG"
BASE_URL = f"https://api.safew.org/bot{BOT_TOKEN}"
DATA_FILE = "data.json"
GROUP_ID = -10000602092

ADMIN_IDS = [13227717]
EXCLUDE_NAMES = ["Ellen匪", "表", "雨夜带刀不带伞", "红牛", "二东", "阿航", "大力出奇迹", "蓝心羽"]
NEW_MEMBERS_FILE = "new_members.json"

# 固定人员名单（已包含鹏、小韩、小黑）
FIXED_USERS = {
    "天洋": "13440085", "小凯": "13440486", "小明": "13234569", "林云": "13321501",
    "林强": "13235219", "小飞": "13235403", "小涛": "13234715", "招财": "13234945",
    "路克": "13235100", "甄子丹": "13235185", "啊朕": "13233448", "阿鬼": "13198948",
    "2胖": "13198655", "黑龙": "13326014", "太阳": "13327822", "晴天": "13234468",
    "罗杰": "13200020", "阿火": "13234881", "胖胖": "13198739", "小二": "13198841",
    "南": "13233106", "振亮": "13198523", "冰岛": "13235012", "九": "13198171",
    "小康": "13234840", "阿枫": "13321490", "毛毛": "13233117", "阿飞": "13232756",
    "阿乐": "10515461", "星辰": "13198685", "旺仔": "13305478", "大蛇": "13233303",
    "舒克": "13233506", "安仔": "13199957", "南宫": "13234669", "阿超": "13233739",
    "小九": "13317648", "老二": "13234476", "阿宇": "13425919",
    "鹏": "13503369", "小韩": "13503345", "小黑": "13503470"
}

KEYBOARD = {
    "keyboard": [["上班", "下班"], ["吃饭", "上厕所", "抽烟"], ["其他", "回座"]],
    "resize_keyboard": True
}

# ========== 新成员管理（支持日期过滤） ==========
def load_new_members():
    """加载新成员数据，兼容旧格式（字符串 -> 转换为新格式）"""
    if not os.path.exists(NEW_MEMBERS_FILE):
        return {}
    with open(NEW_MEMBERS_FILE, "r") as f:
        raw = json.load(f)
    converted = {}
    for name, value in raw.items():
        if isinstance(value, str):
            # 旧格式：直接是ID，设置加入日期为2000-01-01（保证始终有效）
            converted[name] = {"id": value, "join_date": "2000-01-01"}
        else:
            converted[name] = value
    return converted

def save_new_members(members):
    with open(NEW_MEMBERS_FILE, "w") as f:
        json.dump(members, f, ensure_ascii=False, indent=2)

def get_users_for_date(target_date):
    """
    返回指定日期应参与考勤的人员字典 {姓名: 用户ID}
    规则：固定成员全部包含 + 新成员中 join_date <= target_date 的成员
    """
    all_users = FIXED_USERS.copy()
    new_members = load_new_members()
    for name, info in new_members.items():
        join_date = info.get("join_date")
        if join_date and join_date <= target_date:
            # 如果固定名单中已有同名成员，以固定名单为准（不覆盖）
            if name not in all_users:
                all_users[name] = info["id"]
    return all_users

def auto_add_user(user_id, user_name):
    """自动添加新成员，记录加入日期为当天（UTC+8日期）"""
    if user_name in EXCLUDE_NAMES:
        return False
    if user_name in FIXED_USERS or user_id in FIXED_USERS.values():
        return False

    new_members = load_new_members()
    # 检查是否已存在（通过姓名或ID）
    for name, info in new_members.items():
        if name == user_name or info["id"] == user_id:
            return False

    today = beijing_now().strftime("%Y-%m-%d")   # 加入日期
    new_members[user_name] = {"id": user_id, "join_date": today}
    save_new_members(new_members)
    log_print(f"📝 自动添加新成员: {user_name} ({user_id}) 加入日期 {today}，明天起纳入考勤")
    for admin_id in ADMIN_IDS:
        send(admin_id, f"📝 新成员自动加入考勤名单\n👤 姓名：{user_name}\n🆔 ID：{user_id}\n📅 加入日期：{today}\n⏳ 从明天起纳入考勤统计")
    return True

# ========== 基础函数 ==========
def load():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

def send(chat_id, text):
    try:
        url = f"{BASE_URL}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "disable_notification": True}
        if "📋" in text:
            payload["reply_markup"] = KEYBOARD
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        log_print(f"发送消息失败: {e}", "error")

def send_long_message(chat_id, text, max_len=4096):
    if len(text) <= max_len:
        send(chat_id, text)
        return
    lines = text.split('\n')
    employee_indices = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9]+：$', stripped):
            employee_indices.append(i)
    if len(employee_indices) < 2:
        current_page = ""
        for line in lines:
            if len(current_page) + len(line) + 1 > max_len:
                send(chat_id, current_page)
                current_page = line
            else:
                current_page = current_page + "\n" + line if current_page else line
        if current_page:
            send(chat_id, current_page)
        return
    header_end = employee_indices[0]
    header_text = '\n'.join(lines[:header_end])
    employee_indices.append(len(lines))
    employee_blocks = []
    for idx in range(len(employee_indices) - 1):
        start = employee_indices[idx]
        end = employee_indices[idx + 1]
        employee_blocks.append('\n'.join(lines[start:end]))
    pages = []
    current_page = header_text
    for block in employee_blocks:
        if len(current_page) + len(block) + 2 > max_len and len(current_page) > len(header_text):
            pages.append(current_page)
            current_page = block
        else:
            current_page = current_page + "\n\n" + block if current_page else block
    if current_page:
        pages.append(current_page)
    for i, page in enumerate(pages, 1):
        if len(pages) > 1:
            page += f"\n\n--- 第 {i}/{len(pages)} 页 ---"
        send(chat_id, page)
        time.sleep(0.3)

def fmt(seconds):
    if seconds < 0:
        seconds = 0
    if seconds < 60:
        return f"{seconds}秒"
    m = seconds // 60
    s = seconds % 60
    if s == 0:
        return f"{m}分钟"
    return f"{m}分{s}秒"

def get_full_attendance_report():
    db = load()
    now = beijing_now()
    # 业务日期：凌晨3点前算前一天
    if now.hour < 3:
        report_date = now - timedelta(days=1)
    else:
        report_date = now
    today_str = report_date.strftime("%Y-%m-%d")
    weekday = report_date.weekday()

    # 获取该日期有效的所有人员（固定成员始终有效，新成员按加入日期过滤）
    all_users = get_users_for_date(today_str)

    if weekday == 6:
        deadline = report_date.replace(hour=12, minute=0, second=0, microsecond=0)
    else:
        deadline = report_date.replace(hour=9, minute=0, second=0, microsecond=0)

    user_data = {}
    for name, uid in all_users.items():
        if name in EXCLUDE_NAMES:
            continue
        u = db.get(uid, {})
        work_start = u.get("work_start", "")
        check_time = None
        if work_start.startswith(today_str):
            try:
                check_time = datetime.fromisoformat(work_start)
                if check_time.tzinfo is None:
                    check_time = check_time.replace(tzinfo=BEIJING_TZ)
            except:
                pass
        daily_activity = u.get("daily_activity", {})
        total_activity_time = sum(daily_activity.get(act, 0) for act in ["吃饭", "上厕所", "抽烟", "其他"])
        activity_records = u.get("activity_records", [])
        today_records = [r for r in activity_records if r.get("date") == today_str]
        timeout_limits = {"抽烟": 5, "上厕所": 15, "吃饭": 40}
        timeout_records = []
        for record in today_records:
            act = record.get("activity")
            duration = record.get("duration", 0)
            limit = timeout_limits.get(act, 0)
            if limit and duration > limit * 60:
                timeout_records.append({
                    "activity": act,
                    "duration": duration - limit * 60,
                    "time": record.get("time", ""),
                    "total_duration": duration
                })
        counts = {
            "上班次数": u.get("上班次数", 0),
            "下班次数": u.get("下班次数", 0),
            "吃饭次数": u.get("吃饭次数", 0),
            "上厕所次数": u.get("上厕所次数", 0),
            "抽烟次数": u.get("抽烟次数", 0),
            "其他次数": u.get("其他次数", 0),
            "总工作时长": u.get("总工作时长", 0),
            "漏打卡次数": u.get("漏打卡次数", 0),
            "activity_records": today_records,
            "timeout_records": timeout_records
        }
        user_data[name] = {
            "check_time": check_time,
            "total_activity_time": total_activity_time,
            "counts": counts
        }

    on_time_list = []
    late_list = []
    absent_list = []
    for name, data in user_data.items():
        ct = data["check_time"]
        if ct is None:
            absent_list.append(name)
        elif ct <= deadline:
            on_time_list.append((name, ct))
        else:
            late_list.append((name, ct))

    msg = f"📊 今日考勤明细 ({today_str})\n\n"
    if on_time_list:
        msg += f"⏰ 准时 ({len(on_time_list)}人)：\n"
        for name, ct in sorted(on_time_list, key=lambda x: x[1]):
            msg += f"  {name} {ct.strftime('%H:%M:%S')}\n"
        msg += "\n"
    if late_list:
        msg += f"⚠️ 迟到 ({len(late_list)}人)：\n"
        for name, ct in sorted(late_list, key=lambda x: x[1]):
            msg += f"  {name} {ct.strftime('%H:%M:%S')}\n"
        msg += "\n"
    if absent_list:
        msg += f"❌ 缺勤 ({len(absent_list)}人)：\n"
        for name in absent_list:
            msg += f"  {name}（未打卡）\n"
        msg += "\n"

    msg += f"📋 个人活动明细：\n"
    for name in all_users:
        if name in EXCLUDE_NAMES:
            continue
        d = user_data.get(name)
        if not d or (d["check_time"] is None and not d["counts"]["activity_records"] and d["counts"]["漏打卡次数"] == 0):
            continue
        msg += f"\n{name}：\n"
        if d["total_activity_time"] > 0:
            msg += f"  今日活动总时长：{fmt(d['total_activity_time'])}\n"
        for record in d["counts"]["activity_records"]:
            act = record.get("activity")
            duration = record.get("duration", 0)
            limit = {"抽烟": 5, "上厕所": 15, "吃饭": 40}.get(act, 0)
            if limit and duration > limit * 60:
                overtime = duration - limit * 60
                msg += f"  {act}：{fmt(duration)} ⚠️ 超时 {fmt(overtime)}\n"
            else:
                msg += f"  {act}：{fmt(duration)}\n"
        cnt = d["counts"]
        if cnt["漏打卡次数"] > 0:
            msg += f"  ⚠️ 漏打卡次数：{cnt['漏打卡次数']}\n"
        if cnt["timeout_records"]:
            msg += f"  ⚠️ 超时明细：\n"
            idx = 1
            for record in cnt["timeout_records"]:
                total = record.get("total_duration", 0)
                overtime = record.get("duration", 0)
                time_str = record.get("time", "")
                act = record.get("activity", "")
                msg += f"    • 第{idx}次{act}：本次时长 {fmt(total)}，超时 {fmt(overtime)}（{time_str}）\n"
                idx += 1
        if cnt["上班次数"] > 0 or cnt["吃饭次数"] > 0:
            msg += f"  累计：上班{cnt['上班次数']}次，下班{cnt['下班次数']}次"
            if cnt["吃饭次数"] > 0:
                msg += f"，吃饭{cnt['吃饭次数']}次"
            if cnt["上厕所次数"] > 0:
                msg += f"，上厕所{cnt['上厕所次数']}次"
            if cnt["抽烟次数"] > 0:
                msg += f"，抽烟{cnt['抽烟次数']}次"
            msg += "\n"

    total_expected = len([n for n in all_users if n not in EXCLUDE_NAMES])
    total_present = len(on_time_list) + len(late_list)
    msg += f"\n📈 全员汇总：\n"
    msg += f"  应到人数：{total_expected} 人\n"
    msg += f"  实到人数：{total_present} 人\n"
    msg += f"  缺勤人数：{len(absent_list)} 人\n"
    msg += f"  迟到人数：{len(late_list)} 人\n"
    msg += f"\n✅ 统计不影响打卡状态，无需重新打卡"
    return msg

# ========== 定时任务 ==========
def send_reset_report_to_group():
    now = beijing_now()
    report = get_full_attendance_report()
    header = f"📋【今日考勤汇总】即将重置数据\n⏰ 重置时间：{now.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    send_long_message(GROUP_ID, header + report)
    log_print("已发送重置前考勤报告到群组")

def send_reset_report_to_admin():
    now = beijing_now()
    report = get_full_attendance_report()
    header = f"📋【数据备份】即将重置考勤数据\n⏰ 重置时间：{now.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    for admin_id in ADMIN_IDS:
        send_long_message(admin_id, header + report)
    log_print(f"已发送备份考勤报告给 {len(ADMIN_IDS)} 位管理员")

def daily_reset_loop():
    while True:
        now = beijing_now()
        next_reset = now.replace(hour=3, minute=0, second=0, microsecond=0)
        if now >= next_reset:
            next_reset += timedelta(days=1)
        wait_seconds = (next_reset - now).total_seconds()
        log_print(f"距离下次数据重置还有 {wait_seconds/3600:.1f} 小时")
        time.sleep(wait_seconds)
        log_print("准备重置数据，正在发送考勤报告...")
        send_reset_report_to_group()
        time.sleep(2)
        send_reset_report_to_admin()
        time.sleep(2)
        save({})
        log_print("每日考勤数据重置完成")

def schedule_loop():
    while True:
        now = beijing_now()
        if now.hour < 3:
            send_date = now - timedelta(days=1)
        else:
            send_date = now
        send_weekday = send_date.weekday()
        if send_weekday == 6:
            target = now.replace(hour=12, minute=10, second=0, microsecond=0)
        else:
            target = now.replace(hour=9, minute=10, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        wait_seconds = (target - now).total_seconds()
        log_print(f"下次定时统计时间: {target.strftime('%Y-%m-%d %H:%M:%S')}")
        time.sleep(wait_seconds)
        report = get_full_attendance_report()
        send_long_message(GROUP_ID, report)
        log_print("已发送考勤统计到群组")

threading.Thread(target=daily_reset_loop, daemon=True).start()
threading.Thread(target=schedule_loop, daemon=True).start()

log_print("机器人启动...")
log_print("每日凌晨3点重置数据（重置前会发送报告到群组和管理员）")
log_print("周一到周六9:10、周日12:10自动发送考勤统计")
log_print("发送 /sendreport 查看全员个人明细")
log_print("🤖 自动识别新成员：新成员首次打卡时自动加入考勤名单，从第二天起纳入统计")

last_id = 0
while True:
    try:
        resp = requests.get(f"{BASE_URL}/getUpdates", params={"offset": last_id + 1, "timeout": 20})
        if resp.status_code != 200:
            time.sleep(2)
            continue
        data = resp.json()
        if not data.get("ok"):
            time.sleep(2)
            continue
        for update in data.get("result", []):
            last_id = update["update_id"] + 1
            msg = update.get("message")
            if not msg:
                continue
            chat_id = msg["chat"]["id"]
            user_id = str(msg["from"]["id"])
            user_name = msg["from"].get("first_name", "") or str(user_id)
            text = msg.get("text", "").strip()
            auto_add_user(user_id, user_name)
            if text == "/sendreport":
                report = get_full_attendance_report()
                send_long_message(chat_id, report)
                continue
            if text in ["上", "上班"]:
                cmd = "上班"
            elif text in ["下", "下班"]:
                cmd = "下班"
            elif text in ["回", "回座"]:
                cmd = "回座"
            elif text in ["吃", "cf", "吃饭"]:
                cmd = "吃饭"
            elif text in ["厕", "厕所", "wc", "sc", "上厕所"]:
                cmd = "上厕所"
            elif text in ["抽", "cy", "抽烟"]:
                cmd = "抽烟"
            elif text in ["其", "其他", "qt"]:
                cmd = "其他"
            elif text == "/start":
                send(chat_id, f"📋 打卡机器人\n👤 {user_name}\n🆔 {user_id}\n\n上-上班 下-下班 回-回座\n吃/厕/抽/其-活动\n发送 /sendreport 查看全员考勤明细\n\n🤖 新成员首次打卡会自动加入考勤名单，从第二天起纳入统计")
                continue
            else:
                continue

            log_print(f"{user_name}: {cmd}")
            db = load()
            key = user_id
            u = db.get(key, {"state": "off"})
            now = beijing_now()
            ts = now.strftime("%m/%d %H:%M:%S")
            today = now.strftime("%Y-%m-%d")
            state = u.get("state", "off")
            if "activity_records" not in u:
                u["activity_records"] = []
            if "daily_activity" not in u:
                u["daily_activity"] = {}
            daily_activity = u.get("daily_activity", {})
            if u.get("last_date") != today:
                daily_activity = {"吃饭": 0, "上厕所": 0, "抽烟": 0, "其他": 0}
                u["daily_activity"] = daily_activity
                u["activity_records"] = []
                u["last_date"] = today

            if cmd == "上班":
                if state in ["working", "in_activity"]:
                    send(chat_id, f"👤 {user_name}\n🆔 {user_id}\n❌ 上班失败！已在上班中\n请先【下班】")
                else:
                    u = {
                        "state": "working",
                        "work_start": now.isoformat(),
                        "上班次数": u.get("上班次数", 0) + 1,
                        "下班次数": u.get("下班次数", 0),
                        "总工作时长": u.get("总工作时长", 0),
                        "吃饭次数": u.get("吃饭次数", 0),
                        "上厕所次数": u.get("上厕所次数", 0),
                        "抽烟次数": u.get("抽烟次数", 0),
                        "其他次数": u.get("其他次数", 0),
                        "漏打卡次数": u.get("漏打卡次数", 0),
                        "activity_records": u.get("activity_records", []),
                        "daily_activity": daily_activity,
                        "last_date": today
                    }
                    db[key] = u
                    save(db)
                    send(chat_id, f"👤 {user_name}\n🆔 {user_id}\n✅ 上班成功 {ts}\n第{u['上班次数']}次上班")
            elif cmd == "下班":
                if state not in ["working", "in_activity"]:
                    send(chat_id, f"👤 {user_name}\n🆔 {user_id}\n❌ 下班失败！还没上班")
                else:
                    msgs = [f"👤 {user_name}", f"🆔 {user_id}"]
                    if state == "in_activity":
                        act = u.get("activity")
                        astart = datetime.fromisoformat(u["act_start"])
                        adur = int((now - astart).total_seconds())
                        act_count_key = act + "次数"
                        u[act_count_key] = u.get(act_count_key, 0) + 1
                        daily_activity[act] = daily_activity.get(act, 0) + adur
                        activity_records = u.get("activity_records", [])
                        activity_records.append({
                            "date": today,
                            "time": ts,
                            "activity": act,
                            "duration": adur
                        })
                        u["activity_records"] = activity_records
                        msgs.append(f"📝 结束活动：{act}（{fmt(adur)}）")
                    wdur = int((now - datetime.fromisoformat(u["work_start"])).total_seconds())
                    u["总工作时长"] = u.get("总工作时长", 0) + wdur
                    u["下班次数"] = u.get("下班次数", 0) + 1
                    u["daily_activity"] = daily_activity
                    new_u = {
                        "上班次数": u.get("上班次数", 0),
                        "下班次数": u.get("下班次数", 0),
                        "总工作时长": u.get("总工作时长", 0),
                        "吃饭次数": u.get("吃饭次数", 0),
                        "上厕所次数": u.get("上厕所次数", 0),
                        "抽烟次数": u.get("抽烟次数", 0),
                        "其他次数": u.get("其他次数", 0),
                        "漏打卡次数": u.get("漏打卡次数", 0),
                        "activity_records": u.get("activity_records", []),
                        "daily_activity": daily_activity,
                        "last_date": today
                    }
                    db[key] = new_u
                    save(db)
                    msgs.append(f"✅ 下班成功 {ts}")
                    msgs.append(f"本段：{fmt(wdur)}")
                    msgs.append(f"总工作时长：{fmt(new_u['总工作时长'])}")
                    send(chat_id, "\n".join(msgs))
            elif cmd == "回座":
                if state == "off":
                    send(chat_id, f"👤 {user_name}\n🆔 {user_id}\n❌ 请先【上班】")
                elif state != "in_activity":
                    u["漏打卡次数"] = u.get("漏打卡次数", 0) + 1
                    db[key] = u
                    save(db)
                    send(chat_id, f"👤 {user_name}\n🆔 {user_id}\n❌ 回座失败！漏打卡\n没有进行中的活动\n📊 今日漏打卡次数：{u['漏打卡次数']}")
                else:
                    act = u.get("activity")
                    astart = datetime.fromisoformat(u["act_start"])
                    adur = int((now - astart).total_seconds())
                    act_count_key = act + "次数"
                    u[act_count_key] = u.get(act_count_key, 0) + 1
                    daily_activity[act] = daily_activity.get(act, 0) + adur
                    activity_records = u.get("activity_records", [])
                    activity_records.append({
                        "date": today,
                        "time": ts,
                        "activity": act,
                        "duration": adur
                    })
                    u["activity_records"] = activity_records
                    u["state"] = "working"
                    u.pop("activity", None)
                    u.pop("act_start", None)
                    u["daily_activity"] = daily_activity
                    db[key] = u
                    save(db)
                    send(chat_id,
                        f"👤 {user_name}\n"
                        f"🆔 {user_id}\n"
                        f"✅ 回座成功\n"
                        f"活动：{act}\n"
                        f"本次时长：{fmt(adur)}\n"
                        f"第{u[act_count_key]}次{act}\n"
                        f"今日{act}总时长：{fmt(daily_activity.get(act, 0))}")
            elif cmd in ["吃饭", "上厕所", "抽烟", "其他"]:
                if state == "in_activity":
                    send(chat_id, f"👤 {user_name}\n🆔 {user_id}\n❌ 请先【回座】结束当前活动")
                elif state != "working":
                    send(chat_id, f"👤 {user_name}\n🆔 {user_id}\n❌ 请先【上班】")
                else:
                    u["state"] = "in_activity"
                    u["activity"] = cmd
                    u["act_start"] = now.isoformat()
                    db[key] = u
                    save(db)
                    cnt = u.get(cmd + "次数", 0) + 1
                    limit_msg = ""
                    if cmd == "吃饭":
                        limit_msg = "⚠️ 超过40分钟算超时"
                    elif cmd == "上厕所":
                        limit_msg = "⚠️ 超过15分钟算超时"
                    elif cmd == "抽烟":
                        limit_msg = "⚠️ 超过5分钟算超时"
                    send(chat_id, f"👤 {user_name}\n🆔 {user_id}\n✅ 开始{cmd} {ts}\n第{cnt}次{cmd}\n{limit_msg}")
        time.sleep(0.5)
    except Exception as e:
        log_print(f"主循环错误: {e}", "error")
        time.sleep(3)

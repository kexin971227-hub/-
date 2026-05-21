import json
import os
import requests
from datetime import datetime, timedelta
import time
import threading

BOT_TOKEN = "13243514:3DFu4gK87ZWCPu4nWdLWY21Q4mZy2DgZZBG"
BASE_URL = f"https://api.safew.org/bot{BOT_TOKEN}"
DATA_FILE = "data.json"
GROUP_ID = -10000602092

# 应到人员名单（姓名 -> ID 映射）
FIXED_USERS = {
    "小明": "13234569",
    "林云": "13321501",
    "林强": "13235219",
    "小飞": "13235403",
    "小涛": "13234715",
    "甄子丹": "13234945",
    "路克": "13235100",
    "招财": "13235185",
    "啊朕": "13233448",
    "阿鬼": "13198948",
    "2胖": "13198655",
    "黑龙": "13326014",
    "太阳": "13327822",
    "晴天": "13234468",
    "罗杰": "13200020",
    "阿火": "13234881",
    "胖胖": "13198739",
    "小二": "13198841",
    "南": "13233106",
    "振亮": "13198523",
    "冰岛": "13235012",
    "九": "13198171",
    "小康": "13234840",
    "阿枫": "13321490",
    "毛毛": "13233117",
    "阿飞": "13232756",
    "蓝心羽": "13232984",
    "阿乐": "10515461",
    "星辰": "13198685",
    "旺仔": "13305478",
    "大蛇": "13233303",
    "舒克": "13233506",
    "安仔": "13199957",
    "南宫": "13234669",
    "阿超": "13233739",
    "小九": "13317648",
    "老二": "13234476"
}

EXCLUDE_NAMES = ["Ellen匪", "表", "雨夜带刀不带伞", "红牛", "二东", "阿航", "大力出奇迹"]

KEYBOARD = {
    "keyboard": [
        ["上班", "下班"],
        ["吃饭", "上厕所", "抽烟"],
        ["其他", "回座"]
    ],
    "resize_keyboard": True
}

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
    except:
        pass

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

def get_timeout_info(activity, seconds):
    limits = {"抽烟": 5, "上厕所": 15, "吃饭": 30}
    limit = limits.get(activity, 0)
    if limit and seconds > limit * 60:
        overtime = seconds - limit * 60
        return f"{fmt(seconds)} ⚠️ 超时 {fmt(overtime)}"
    return fmt(seconds)

def get_full_attendance_report():
    """生成全员个人明细考勤报告"""
    db = load()
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    weekday = now.weekday()
    
    if weekday == 6:
        deadline = now.replace(hour=12, minute=0, second=0, microsecond=0)
    else:
        deadline = now.replace(hour=9, minute=0, second=0, microsecond=0)
    
    # 收集每个人的数据
    user_data = {}
    for name, uid in FIXED_USERS.items():
        if name in EXCLUDE_NAMES:
            continue
        u = db.get(uid, {})
        work_start = u.get("work_start", "")
        check_time = None
        if work_start.startswith(today):
            try:
                check_time = datetime.fromisoformat(work_start)
            except:
                check_time = deadline
        
        # 活动统计
        daily_activity = u.get("daily_activity", {})
        activities = {}
        total_activity_time = 0
        for act in ["吃饭", "上厕所", "抽烟", "其他"]:
            duration = daily_activity.get(act, 0)
            if duration > 0:
                activities[act] = duration
                total_activity_time += duration
        
        # 次数统计
        counts = {
            "上班次数": u.get("上班次数", 0),
            "下班次数": u.get("下班次数", 0),
            "吃饭次数": u.get("吃饭次数", 0),
            "上厕所次数": u.get("上厕所次数", 0),
            "抽烟次数": u.get("抽烟次数", 0),
            "其他次数": u.get("其他次数", 0),
            "总工作时长": u.get("总工作时长", 0)
        }
        
        user_data[name] = {
            "check_time": check_time,
            "activities": activities,
            "total_activity_time": total_activity_time,
            "counts": counts
        }
    
    # 分类：准时、迟到、缺勤
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
    
    # 生成报告
    msg = f"📊 今日考勤明细 ({today})\n\n"
    
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
    
    # 个人活动明细
    msg += f"📋 个人活动明细：\n"
    for name in FIXED_USERS:
        if name in EXCLUDE_NAMES:
            continue
        d = user_data[name]
        if d["check_time"] is None and not d["activities"]:
            continue  # 完全没数据的跳过
        
        msg += f"\n{name}：\n"
        if d["total_activity_time"] > 0:
            msg += f"  今日活动总时长：{fmt(d['total_activity_time'])}\n"
        for act, dur in d["activities"].items():
            msg += f"  {act}：{fmt(dur)}\n"
        
        # 显示次数统计（如果有）
        cnt = d["counts"]
        if cnt["上班次数"] > 0 or cnt["吃饭次数"] > 0:
            msg += f"  累计：上班{cnt['上班次数']}次，下班{cnt['下班次数']}次"
            if cnt["吃饭次数"] > 0:
                msg += f"，吃饭{cnt['吃饭次数']}次"
            if cnt["上厕所次数"] > 0:
                msg += f"，上厕所{cnt['上厕所次数']}次"
            if cnt["抽烟次数"] > 0:
                msg += f"，抽烟{cnt['抽烟次数']}次"
            msg += "\n"
    
    # 汇总统计
    total_expected = len([n for n in FIXED_USERS if n not in EXCLUDE_NAMES])
    total_present = len(on_time_list) + len(late_list)
    msg += f"\n📈 全员汇总：\n"
    msg += f"  应到人数：{total_expected} 人\n"
    msg += f"  实到人数：{total_present} 人\n"
    msg += f"  缺勤人数：{len(absent_list)} 人\n"
    msg += f"  迟到人数：{len(late_list)} 人\n"
    
    msg += f"\n✅ 统计不影响打卡状态，无需重新打卡"
    return msg

def daily_reset_loop():
    while True:
        now = datetime.now()
        next_reset = now.replace(hour=3, minute=0, second=0, microsecond=0)
        if now >= next_reset:
            next_reset += timedelta(days=1)
        wait_seconds = (next_reset - now).total_seconds()
        print(f"距离下次数据重置还有 {wait_seconds/3600:.1f} 小时")
        time.sleep(wait_seconds)
        save({})
        print("每日考勤数据重置完成")

def schedule_loop():
    while True:
        now = datetime.now()
        weekday = now.weekday()
        if weekday == 6:
            target = now.replace(hour=12, minute=10, second=0, microsecond=0)
        else:
            target = now.replace(hour=9, minute=10, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        wait_seconds = (target - now).total_seconds()
        print(f"下次统计时间: {target.strftime('%Y-%m-%d %H:%M:%S')}")
        time.sleep(wait_seconds)
        report = get_full_attendance_report()
        send(GROUP_ID, report)
        print("已发送考勤统计到群组")

threading.Thread(target=daily_reset_loop, daemon=True).start()
threading.Thread(target=schedule_loop, daemon=True).start()

print("机器人启动...")
print("每日凌晨3点重置数据")
print("周一到周六9:10、周日12:10自动发送考勤统计")
print("发送 /sendreport 查看全员个人明细")

last_id = 0
keyboard_activated = set()

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
            
            if text == "/sendreport":
                report = get_full_attendance_report()
                send(chat_id, report)
                continue
            
            if text in ["上", "上班"]:
                cmd = "上班"
            elif text in ["下", "下班"]:
                cmd = "下班"
            elif text in ["回", "回座"]:
                cmd = "回座"
            elif text in ["吃", "吃饭"]:
                cmd = "吃饭"
            elif text in ["厕", "上厕所"]:
                cmd = "上厕所"
            elif text in ["抽", "抽烟"]:
                cmd = "抽烟"
            elif text in ["其", "其他"]:
                cmd = "其他"
            elif text == "/start":
                send(chat_id, f"📋 打卡机器人\n👤 {user_name}\n🆔 {user_id}\n\n上-上班 下-下班 回-回座\n吃/厕/抽/其-活动\n发送 /sendreport 查看全员考勤明细")
                continue
            else:
                continue
            
            print(f"{user_name}: {cmd}")
            
            db = load()
            key = user_id
            u = db.get(key, {"state": "off"})
            
            now = datetime.now()
            ts = now.strftime("%m/%d %H:%M:%S")
            today = now.strftime("%Y-%m-%d")
            state = u.get("state", "off")
            
            if "daily_activity" not in u:
                u["daily_activity"] = {}
            daily_activity = u.get("daily_activity", {})
            
            if u.get("last_date") != today:
                daily_activity = {"吃饭": 0, "上厕所": 0, "抽烟": 0, "其他": 0}
                u["daily_activity"] = daily_activity
                u["last_date"] = today
            
            # 上班
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
                        "daily_activity": daily_activity,
                        "last_date": today
                    }
                    db[key] = u
                    save(db)
                    send(chat_id, f"👤 {user_name}\n🆔 {user_id}\n✅ 上班成功 {ts}\n第{u['上班次数']}次上班")
            
            # 下班
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
                        msgs.append(f"📝 结束活动：{act}（{get_timeout_info(act, adur)}）")
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
                        "daily_activity": daily_activity,
                        "last_date": today
                    }
                    db[key] = new_u
                    save(db)
                    msgs.append(f"✅ 下班成功 {ts}")
                    msgs.append(f"本段：{fmt(wdur)}")
                    msgs.append(f"总工作时长：{fmt(new_u['总工作时长'])}")
                    send(chat_id, "\n".join(msgs))
            
            # 回座
            elif cmd == "回座":
                if state != "in_activity":
                    send(chat_id, f"👤 {user_name}\n🆔 {user_id}\n❌ 没有进行中的活动")
                else:
                    act = u.get("activity")
                    astart = datetime.fromisoformat(u["act_start"])
                    adur = int((now - astart).total_seconds())
                    act_count_key = act + "次数"
                    u[act_count_key] = u.get(act_count_key, 0) + 1
                    daily_activity[act] = daily_activity.get(act, 0) + adur
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
                        f"本次时长：{get_timeout_info(act, adur)}\n"
                        f"第{u[act_count_key]}次{act}\n"
                        f"今日{act}总时长：{fmt(daily_activity.get(act, 0))}")
            
            # 活动
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
                        limit_msg = "⚠️ 超过30分钟算超时"
                    elif cmd == "上厕所":
                        limit_msg = "⚠️ 超过15分钟算超时"
                    elif cmd == "抽烟":
                        limit_msg = "⚠️ 超过5分钟算超时"
                    send(chat_id, f"👤 {user_name}\n🆔 {user_id}\n✅ 开始{cmd} {ts}\n第{cnt}次{cmd}\n{limit_msg}")
        
        time.sleep(0.5)
        
    except Exception as e:
        print(f"错误: {e}")
        time.sleep(3)  

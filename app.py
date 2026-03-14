# SmartForward - WhatsApp Email Forwarder
#main
import imaplib
import mimetypes
import email
import time
import random
import os
import razorpay
import threading
import smtplib
import requests
from PIL import Image
from email.mime.text import MIMEText
from flask import Flask, request, session, redirect,render_template
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from cryptography.fernet import Fernet
from security_layers import total_security_score
# -------- Load ENV --------
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
cipher = Fernet(SECRET_KEY)
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
RAZORPAY_KEY = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY, RAZORPAY_SECRET))

# -------- MongoDB --------
client = MongoClient(
    MONGO_URI,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000
)

db = client["SmartForward"]
users_collection = db["users"]
emails_collection = db["emails"]
emails_collection.create_index("wa_message_id")
emails_collection.create_index("email_uid")
users_collection.create_index("phone")

# -------- Globals --------
last_email_ids = {}

# -------- WhatsApp --------
def send_whatsapp(phone, message, sender=None, subject=None, email_user=None, email_uid=None):
    try:

        url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"

        headers = {
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }

        data = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {
                    "text": message
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "archive_email",
                                "title": "Archive"
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "spam_email",
                                "title": "Spam"
                            }
                        }
                    ]
                }
            }
        }

        res = requests.post(url, headers=headers, json=data, timeout=10)
        response = res.json()
        print("WhatsApp API response:", response)

        if "messages" in response:

            message_id = response["messages"][0]["id"]

            emails_collection.insert_one({
                "wa_message_id": message_id,
                "email_uid": email_uid,
                "sender": sender or "",
                "subject": subject or "",
                "email": email_user,
                "phone": phone
            })

        else:
            print("WhatsApp API error:", response)

    except Exception as e:
        print("WA Error:", e)


# -------- WhatsApp OTP --------

def send_whatsapp_otp(phone, message):
    url = f"https://graph.facebook.com/v18.0/{os.getenv('PHONE_NUMBER_ID')}/messages"

    headers = {
        "Authorization": f"Bearer {os.getenv('ACCESS_TOKEN')}",
        "Content-Type": "application/json"
    }

    data = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {
            "body": message
        }
    }

    response = requests.post(url, headers=headers, json=data)

    print(response.text)
    
    
#-------- Compress Image if larger than 4MB --------

def compress_image(file_path, max_size_kb=4000):

    img = Image.open(file_path)

    compressed_path = file_path.replace(".jpg", "_compressed.jpg")

    quality = 85

    while True:
        img.save(compressed_path, "JPEG", quality=quality)

        if os.path.getsize(compressed_path) <= max_size_kb * 1024:
            break

        quality -= 5

        if quality <= 20:
            break

    return compressed_path
    
#-------- Send Media --------
    
def send_whatsapp_media(phone, file_path):
    
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/media"

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }

    mime_type = mimetypes.guess_type(file_path)[0]

    if mime_type and mime_type.startswith("image"):
        file_path = compress_image(file_path)
        mime_type = mimetypes.guess_type(file_path)[0]

    if not mime_type:
        mime_type = "application/octet-stream"
    
    print("sending file:", file_path)
    print("mime type:", mime_type)

    # -------- Upload file to WhatsApp --------
    with open(file_path, "rb") as f:

        files = {
            "file": (os.path.basename(file_path), f, mime_type),
            "messaging_product": (None, "whatsapp")
        }

        res = requests.post(url, headers=headers, files=files)

    print("MEDIA UPLOAD:", res.text)

    media_id = res.json().get("id")

    if not media_id:
        print("Media upload failed")
        return

    # -------- Detect file type --------
    ext = file_path.split(".")[-1].lower()

    send_url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"

    # -------- IMAGE --------
    if mime_type and mime_type.startswith("image"):

        data = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "image",
            "image": {
                "id": media_id
            }
        }

    # -------- DOCUMENT --------
    else:

        data = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "document",
            "document": {
                "id": media_id,
                "filename": os.path.basename(file_path)
            }
        }

    response = requests.post(
        send_url,
        headers={
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "application/json"
        },
        json=data
    )

    print("MEDIA SENT:", response.text)
    
#-------- Reopen Template --------
def send_reopen_template(phone):
    
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    data = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "template",
        "template": {
            "name": "email_alert",
            "language": {"code": "en"}
        }
    }

    response = requests.post(url, headers=headers, json=data)
    print("TEMPLATE RESPONSE:",response.text)


# -------- Email helpers --------
def get_subject(msg):
    return msg["subject"] or "No Subject"


def get_email_body(msg):
    body = ""

    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                body = part.get_payload(decode=True).decode(errors="ignore")
                break
    else:
        body = msg.get_payload(decode=True).decode(errors="ignore")

    return body

# ------- Get Attachments --------

def get_attachments(msg):
    
    files = []

    for part in msg.walk():

        filename = part.get_filename()

        if filename:

            filepath = f"/tmp/{filename}"

            with open(filepath, "wb") as f:
                f.write(part.get_payload(decode=True))

            files.append(filepath)

    return files


# -------- Session Check --------

def is_session_active(user):
    
    last = user.get("last_user_message")

    if not last:
        return False

    diff = datetime.utcnow() - last

    return diff.total_seconds() < 86400

# -------- Email Reply --------
def send_email_reply(email_user, password, to_email, subject, body):
    try:
        if not to_email:
            print("sender email missing")
            return
        if "<" in to_email:
            to_email = to_email.split("<")[-1].replace(">", "").strip()
        
        msg = MIMEText(body)
        msg["From"] = email_user
        msg["To"] = to_email
        msg["Subject"] = "Re: " + subject

        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=15)
        server.starttls()
        server.login(email_user, password)
        server.sendmail(email_user, to_email, msg.as_string())
        server.quit()

    except Exception as e:
        print("Email error:", e)


# ------- Move Email --------

def move_email(email_user, password, email_uid, folder):
    
    try:

        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(email_user, password)
        mail.select("INBOX")

        if folder == "spam":
            mail.store(email_uid, '+X-GM-LABELS', '\\Spam')

        if folder == "archive":
            mail.store(email_uid, '+X-GM-LABELS', '\\All')

        mail.logout()

    except Exception as e:
        print("Move email error:", e)

# -------- Check Email --------
def check_single_user(EMAIL, PASSWORD, PHONE, user):
    try:

        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL, PASSWORD)
        mail.select("INBOX")

        status, data = mail.search(None, "UNSEEN")
        email_ids = data[0].split()

        if not email_ids:
            mail.logout()
            return

        for latest in email_ids[-5:]:   # last 5 emails process

            # Duplicate protection
            existing = emails_collection.find_one({
                "email_uid": latest,
                "phone": PHONE
            })

            if existing:
                print("Duplicate email skipped")
                continue

            status, msg_data = mail.fetch(latest, "(RFC822)")

            for response in msg_data:

                if not isinstance(response, tuple):
                    continue

                msg = email.message_from_bytes(response[1])

                print("DEBUG ATTACHMENT CHECK:")
                attachments = get_attachments(msg)
                print("ATTACHMENTS:", attachments)

                email_time = parsedate_to_datetime(msg.get("date"))
                email_time = email_time.strftime("%d %b %y | %I:%M %p")

                subject = get_subject(msg)
                body = get_email_body(msg)

                # -------- Sender Clean --------
                sender = msg.get("from") or ""

                if "<" in sender:
                    sender = sender.split("<")[-1].replace(">", "").strip()

                print("SENDER EMAIL:", sender)

                print("EMAIL CHECKED:", subject)

                score = total_security_score(subject, body, sender, attachments, msg, db)

                preview = body.replace("\n", " ").replace("\r", " ")
                preview = preview[:350] + "..." if len(preview) > 350 else preview

                users_collection.update_one(
                    {"phone": PHONE},
                    {"$set": {
                        "last_sender_email": sender,
                        "last_subject": subject
                    }}
                )

                message = f"""📬 *New Email*
👤 *Sender:* {sender}
📌 *Subject:* {subject}
⏰ *Received:* {email_time}
⚠ *Scam Score:* {score}%
━━━━━━━━━━━━━━
📄 *Preview*
{preview}
💬 Reply to this message to respond
"""
                # -------- Subscription limit check --------

                if user.get("emails_used", 0) >= user.get("email_limit", 50):

                    send_whatsapp(
                        PHONE,
                        "⚠ Email limit reached.\nUpgrade your SmartForward plan to continue."
                    )

                    mail.logout()
                    return
                
                if is_session_active(user):

                    send_whatsapp(PHONE, message, sender, subject, EMAIL, latest)
                    # increase email usage
                    users_collection.update_one(
                        {"_id": user["_id"]},
                        {"$inc": {"emails_used": 1}}
                    )

                    # -------- Send Attachments --------
                    if attachments:
                        print("Total Attachments:", len(attachments))

                        time.sleep(2)

                        for index, file in enumerate(attachments):

                            print(f"Sending attachment {index+1}: {file}")

                            send_whatsapp_media(PHONE, file)

                            time.sleep(2)

                            if os.path.exists(file):
                                os.remove(file)

                else:

                    emails_collection.insert_one({
                        "user_id": user["_id"],
                        "sender": sender,
                        "subject": subject,
                        "preview": preview,
                        "status": "pending"
                    })
                    if not user.get("template_sent"):
                        send_reopen_template(PHONE)
                        
                        users_collection.update_one({"_id": user["_id"]},{"$set":{"template_sent":True}})

        mail.logout()

    except Exception as e:
        print("Email check error:", e)


# -------- Check All Users --------
def check_all_users():
    users = users_collection.find({"is_activate": 1})

    for user in users:
        EMAIL = user["email"]
        PASSWORD = cipher.decrypt(user["app_password"].encode()).decode()
        PHONE = user["phone"]

        check_single_user(EMAIL, PASSWORD, PHONE,user)



# -------- Subscription Expiry Check --------
def check_subscription_expiry():

    now = datetime.utcnow()

    expired_users = users_collection.find({
    "$and": [
        {"subscription_end": {"$lt": now}},
        {"subscription_end": {"$ne": None}}
    ]
})

    for user in expired_users:

        users_collection.update_one(
            {"_id": user["_id"]},
            {"$set":{
                "plan":"free",
                "email_limit":10,
                "subscription_start":None,
                "subscription_end":None,
                "subscription_status":"expired"
            }}
        )

        print("Subscription expired:", user["email"])

# -------- Background Worker --------
def email_monitor():
    while True:

        try:
            check_subscription_expiry()
            # -------- Monthly email reset --------
            today = datetime.utcnow()

            if today.day == 1 and today.hour == 0:

                users_collection.update_many(
                    {},
                    {"$set": {"emails_used": 0}}
                )

                print("Monthly email usage reset")
            print("Checking emails...")
            check_all_users()

        except Exception as e:
            print("Worker error:", e)

        time.sleep(60)


# -------- Flask --------
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET")

@app.route("/")
def home():
  return render_template("landing.html")

@app.route("/signup-page")
def signup_page():
    return render_template("signup.html")

# -------- Signup --------
@app.route("/signup", methods=["POST"])
def signup():
    email_id = request.form.get("email")
    password = request.form.get("app_password")
    encrypted_password = cipher.encrypt(password.encode()).decode()
    phone = request.form.get("phone")

    if not email_id or not password or not phone:
        return {"error": "missing fields"}, 400

    otp = str(random.randint(100000, 999999))

    expiry = datetime.utcnow() + timedelta(minutes=5)

    users_collection.update_one(
        {"phone": phone},
        {"$set": {
            "email": email_id,
            "app_password": encrypted_password,
            "phone": phone,
            "otp": otp,
            "otp_expiry": expiry,
            "is_activate": 0,
            "template_sent": False,

            # subscription fields
            "plan": "free",
            "email_limit": 10,
            "emails_used": 0,
            "subscription_start": datetime.utcnow(),
            "subscription_end": None,
            "subscription_status": "active",
            "created_at": datetime.utcnow()
        }},
        upsert=True
    )

    send_whatsapp_otp(phone, f"Your SmartForward OTP is {otp}")

    return render_template("verify_otp.html", phone=phone)

# --------- Verify OTP --------

@app.route("/verify-otp", methods=["POST"])
def verify_otp():

    phone = request.form.get("phone")
    otp = request.form.get("otp")

    user = users_collection.find_one({"phone": phone})

    if not user:
        return "User not found"

    otp_expiry = user.get("otp_expiry")

    if not otp_expiry:
        return "OTP expired or invalid"

    if datetime.utcnow() > otp_expiry:
        return "OTP expired"

    if user.get("otp") != otp:
        return "Invalid OTP"

    users_collection.update_one(
        {"phone": phone},
        {"$set": {"is_activate": 1},
         "$unset": {"otp": "", "otp_expiry": ""}}
    )

    return redirect("/user")

# -------- Webhook --------
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    VERIFY_TOKEN = "smartforward123"

    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200

    return "Verification failed", 403


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    try:

        entry = data.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})

        if "messages" in value:

            msg = value["messages"][0]
            sender_phone = msg.get("from")
            print("USER MESSAGE:", msg)
            print("PHONE:", sender_phone)
            users_collection.update_one(
                {"phone": sender_phone},
                {"$set": {"last_user_message": datetime.utcnow(),"template_sent":False}}
            )

            user = users_collection.find_one({"phone": sender_phone})
            if msg["type"] == "text":
                text = msg.get("text", {}).get("body", "")
                if user:
                    pending_emails = emails_collection.find({
                        "user_id": user["_id"],
                        "status": "pending"
                    })

                    for email in pending_emails:

                        message = f"""📬 *Missed Email*
👤 *Sender:* {email['sender']}
📌 *Subject:* {email['subject']}
⏰ *Received:* {email['email_time']}
⚠ *Scam Score:* {email['score']}%
━━━━━━━━━━━━━━
📄 *Preview*
{email['preview']}
💬 Reply to this message to respond
"""

                        send_whatsapp(sender_phone, message)

                        emails_collection.update_one(
                            {"_id": email["_id"]},
                            {"$set": {"status": "sent"}}
                        )

            # TEXT MESSAGE
            if msg["type"] == "text":

                text = msg.get("text", {}).get("body", "")
                context = msg.get("context", {})
                reply_to_id = context.get("id")

                if user and reply_to_id:

                    email_data = emails_collection.find_one({
                        "wa_message_id": reply_to_id
                    })
                    if email_data and email_data.get("sender"):
                        threading.Thread(
                            target=send_email_reply,
                            args=(
                                user["email"],
                                cipher.decrypt(user["app_password"].encode()).decode(),
                                email_data["sender"],
                                email_data["subject"],
                                text
                            ),
                            daemon=True
                        ).start()
            # TEMPLATE BUTTON CLICK (Open Inbox)
            if msg["type"] == "button":

                payload = msg["button"]["payload"]

                if payload == "Open Inbox" and user:

                    pending_emails = emails_collection.find({
                        "user_id": user["_id"],
                        "status": "pending"
                    })

                    for email in pending_emails:

                        message = f"""
            📬 Missed Email

            Sender: {email['sender']}
            Subject: {email['subject']}

            Reply to respond
            """

                        send_whatsapp(sender_phone, message)

                        emails_collection.update_one(
                            {"_id": email["_id"]},
                            {"$set": {"status": "sent"}}
                        )
            # BUTTON CLICK
            if msg["type"] == "interactive":

                button_id = msg["interactive"]["button_reply"]["id"]

                email_data = emails_collection.find_one({
                    "wa_message_id": msg["context"]["id"]
                })

                if not email_data:
                    return "ok"

                email_uid = email_data["email_uid"]

                if button_id == "spam_email":
                    threading.Thread(
                        target=move_email,
                        args=(user["email"], cipher.decrypt(user["app_password"].encode()).decode(), email_uid, "spam"),
                        daemon=True
                    ).start()

                if button_id == "archive_email":
                    threading.Thread(
                        target=move_email,
                        args=(user["email"], cipher.decrypt(user["app_password"].encode()).decode(), email_uid, "archive"),
                        daemon=True
                    ).start()


    except Exception as e:
        print("Webhook error:", e)

    return "ok"

# -------- Razorpay Webhook --------

@app.route("/razorpay-webhook", methods=["POST"])
def razorpay_webhook():

    data = request.json

    event = data.get("event")

    if event == "payment.captured":

        payment = data["payload"]["payment"]["entity"]

        order_id = payment["order_id"]

        print("Payment success:", order_id)

    return "ok"


# -------- Admin login --------

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":

        password = request.form.get("password")

        if password == ADMIN_PASSWORD:

            session["admin"] = True

            return redirect("/dashboard")

        else:
            return "Wrong password"

    return render_template("admin_login.html")
# -------- Admin Dashboard --------

@app.route("/dashboard")
def dashboard():

    if not session.get("admin"):
        return redirect("/admin")

    search = request.args.get("search")

    if search:
        users = list(users_collection.find({
            "$or": [
                {"email": {"$regex": search, "$options": "i"}},
                {"phone": {"$regex": search, "$options": "i"}}
            ]
        }))
    else:
        users = list(users_collection.find())

    total = users_collection.count_documents({})
    growth = []

    for i in range(7):

        day = datetime.utcnow() - timedelta(days=i)

        count = users_collection.count_documents({
            "created_at": {
                "$gte": day.replace(hour=0, minute=0, second=0),
                "$lt": day.replace(hour=23, minute=59, second=59)
            }
        })

        growth.append(count)

    growth.reverse()
    revenue = 0
    for u in users_collection.find():
        revenue += u.get("total_spent", 0)

    active_users = users_collection.count_documents({
        "is_activate": 1,
        "suspicious": {"$ne": True}
    })

    inactive_users = users_collection.count_documents({
        "is_activate": 0,
        "suspicious": {"$ne": True}
    })

    suspicious_users = users_collection.count_documents({
        "suspicious": True
    })

    return render_template(
        "admin_dashboard.html",
        users=users,
        total=total,
        active_users=active_users,
        inactive_users=inactive_users,
        suspicious_users=suspicious_users,
        revenue=revenue,
        growth=growth,
        now=datetime.utcnow()
    )

# -------- Logout --------

@app.route("/logout")
def logout():
    session.clear()

    return redirect("/admin")

# -------- toggle --------

@app.route("/toggle/<user_id>")
def toggle(user_id):

    if not session.get("admin"):
        return redirect("/admin")

    user = users_collection.find_one({"_id": ObjectId(user_id)})

    # अगर user suspicious है तो toggle allow नहीं
    if user.get("suspicious"):
        return redirect("/dashboard")

    new_status = 0 if user.get("is_activate") == 1 else 1

    users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"is_activate": new_status}}
    )

    return redirect("/dashboard")

#------suspicious-------

@app.route("/suspicious/<user_id>")
def suspicious(user_id):

    if not session.get("admin"):
        return redirect("/admin")

    user = users_collection.find_one({"_id": ObjectId(user_id)})

    # Toggle suspicious
    new_status = not user.get("suspicious", False)

    users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"suspicious": new_status}}
    )

    return redirect("/dashboard")

# -------- Delete --------
@app.route("/delete/<user_id>")
def delete(user_id):
    if not session.get("admin"):
        return redirect("/admin")

    users_collection.delete_one({"_id": ObjectId(user_id)})

    return redirect("/dashboard")


# -------- User Login --------

@app.route("/user", methods=["GET", "POST"])
def user_login():
    if request.method == "POST":

        email = request.form.get("email")
        password = request.form.get("app_password")

        user = users_collection.find_one({"email": email})

        if not user:
            return "Invalid Login"

        try:
            stored_password = cipher.decrypt(user["app_password"].encode()).decode()
        except:
            return "Password error"

        if password != stored_password:
            return "Invalid Login"

        session["user"] = str(user["_id"])

        return redirect("/user-dashboard")

    return render_template("user.html")

# -------- User Dashboard --------

@app.route("/user-dashboard")
def user_dashboard():

    if not session.get("user"):
        return redirect("/user")

    user = users_collection.find_one({
        "_id": ObjectId(session["user"])
    })

    status = "ACTIVE" if user.get("is_activate") == 1 else "DISABLED"
    if user.get("subscription_status") == "expired":
        status = "EXPIRED"

    plan = user.get("plan","free")
    start = user.get("subscription_start")
    end = user.get("subscription_end")

    days_left = None

    # ---- Days Left ----

    if end:
        days_left = max((end - datetime.utcnow()).days, 0)

    return render_template(
        "user_dashboard.html",
        email=user["email"],
        phone=user["phone"],
        status=status,
        plan=plan,
        start=start,
        end=end,
        days_left=days_left,
        emails_used=user.get("emails_used",0),
        email_limit=user.get("email_limit",5)
    )
    
#---- delete- account-----

@app.route("/delete-account")
def delete_account():
    if not session.get("user"):
        return redirect("/user")

    users_collection.delete_one({
        "_id": ObjectId(session["user"])
    })

    session.pop("user", None)

    return """
<script>
alert("Your account has been deleted successfully");
window.location.href = "/";
</script>
"""


# -------- User Logout --------
@app.route("/user-logout")
def user_logout():
    session.pop("user", None)

    return redirect("/user")

#------ upgrade-plan-------

@app.route("/upgrade-plan")
def upgrade_plan():

    if not session.get("user"):
        return redirect("/user")

    users_collection.update_one(
        {"_id": ObjectId(session["user"])},
        {"$set":{
            "plan":"pro",
            "email_limit":999999,
            "subscription_start":datetime.utcnow(),
            "subscription_end":datetime.utcnow()+timedelta(days=30),
            "subscription_status":"active"
        }}
    )

    return """
<script>
alert("Pro Plan Activated");
window.location.href="/user-dashboard";
</script>
"""

#----- plan ----
@app.route("/plan")
def plans():
    return render_template("plans.html")

#--- plan select-----

@app.route("/subscribe/<plan>")
def subscribe(plan):

    session["selected_plan"] = plan

    return redirect("/payment")

#----payment-----
@app.route("/payment")
def payment():

    if not session.get("user"):
        return redirect("/user")

    plan = session.get("selected_plan")

    if plan == "basic":
        amount = 1000
    elif plan == "pro":
        amount = 2000
    else:
        amount = 0

    order = razorpay_client.order.create({
        "amount": amount,
        "currency": "INR",
        "payment_capture": 1
    })
    session["razorpay_order_id"] = order["id"]

    return render_template(
        "payment.html",
        plan=plan,
        amount=amount,
        order_id=order["id"],
        razorpay_key=RAZORPAY_KEY
    )
    
#-----verify-payment----

@app.route("/verify-payment", methods=["POST"])
def verify_payment():

    data = request.json

    payment_id = data.get("razorpay_payment_id")
    order_id = data.get("razorpay_order_id")
    signature = data.get("razorpay_signature")

    try:

        razorpay_client.utility.verify_payment_signature({
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature
        })

        session["payment_verified"] = True

        return {"status":"success"}

    except:

        return {"status":"failed"}

#----- payment success------
@app.route("/payment-success")
def payment_success():
    if not session.get("payment_verified"):
        return redirect("/plan")

    if not session.get("user"):
        return redirect("/user")

    user_id = ObjectId(session["user"])
    plan = session.get("selected_plan")

    user = users_collection.find_one({"_id": user_id})

    current_end = user.get("subscription_end")

    now = datetime.utcnow()

    # अगर plan active है
    if current_end and current_end > now:
        start_date = current_end
    else:
        start_date = now

    end_date = start_date + timedelta(days=30)

    # plan limits
    if plan == "basic":
        limit = 50
    elif plan == "pro":
        limit = 999999
    else:
        limit = 10
        plan = "free"
        
    price = 0

    if plan == "basic":
        price = 10 
    elif plan == "pro":
        price = 20 

    users_collection.update_one(
        {"_id": user_id},
        {
            "$set": {
                "plan": plan,
                "email_limit": limit,
                "subscription_start": start_date,
                "subscription_end": end_date
            },
            "$inc": {
                "total_spent": price
            }
        }
    )
    session.pop("payment_verified",None)
    session.pop("razorpay_order_id",None)

    return redirect("/user-dashboard")

# -------- Update Profile --------

@app.route("/update-profile", methods=["POST"])
def update_profile():
    if not session.get("user"):
        return redirect("/user")

    phone = request.form.get("phone")
    password = request.form.get("app_password")
    encrypted_password = cipher.encrypt(password.encode()).decode()

    users_collection.update_one(
        {"_id": ObjectId(session["user"])},
        {"$set": {
            "phone": phone,
            "app_password": encrypted_password
        }}
    )

    return redirect("/user-dashboard")



# -------- Privacy Policy --------

@app.route("/privacy")
def privacy():
    return render_template("privacy.html")

# -------- Terms of Service --------

@app.route("/terms")
def terms():
    return render_template("terms.html")

#-------- Data Deletion Request --------

@app.route("/delete")
def delete_data():
    return render_template("delete.html")

# -------- Start worker --------
def start_worker():
    time.sleep(15)
    email_monitor()


threading.Thread(target=start_worker, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
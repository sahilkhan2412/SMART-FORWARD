import joblib

try:
    model = joblib.load("spam_model.pkl")
    vectorizer = joblib.load("vectorizer.pkl")
except:
    model = None
    vectorizer = None


def ml_spam_score(subject, body):

    if not model or not vectorizer:
        return 0

    text = subject + " " + body

    vec = vectorizer.transform([text])

    prediction = model.predict_proba(vec)[0][1]

    return int(prediction * 100)

def domain_reputation(sender):
    
    suspicious_domains = [
        "tempmail.com",
        "mailinator.com",
        "10minutemail.com"
    ]

    if "@" not in sender:
        return 0

    domain = sender.split("@")[1]

    if domain in suspicious_domains:
        return 40

    return 0

import whois
from datetime import datetime


def domain_age_score(sender):

    if "@" not in sender:
        return 0

    domain = sender.split("@")[1]

    try:

        w = whois.whois(domain)

        creation = w.creation_date

        if isinstance(creation, list):
            creation = creation[0]

        age_days = (datetime.utcnow() - creation).days

        if age_days < 30:
            return 60

        if age_days < 180:
            return 30

    except:
        pass

    return 0

def url_reputation(body):
    
    if "http://" in body or "https://" in body:
        return 25

    return 0

def shortlink_score(body):
    
    shortlinks = [
        "bit.ly",
        "tinyurl",
        "t.co",
        "shorturl"
    ]

    for link in shortlinks:

        if link in body:
            return 25

    return 0

def attachment_score(files):
    
    score = 0

    bad_extensions = [
        ".exe",
        ".bat",
        ".scr",
        ".js",
        ".vbs"
    ]

    for f in files:

        for ext in bad_extensions:

            if f.endswith(ext):
                score += 70

    return score

def sender_behavior(sender, db):
    
    count = db.emails.count_documents({
        "sender": sender
    })

    if count > 50:
        return 20

    return 0

import spf


def spf_score(ip, sender):

    try:

        result = spf.check2(ip, sender, sender)

        if result[0] == "fail":
            return 40

    except:
        pass

    return 0


import dkim


def dkim_score(raw_email):

    try:

        if not dkim.verify(raw_email):
            return 40

    except:
        pass

    return 0


import dns.resolver


def dmarc_score(domain):

    try:

        records = dns.resolver.resolve(f"_dmarc.{domain}", "TXT")

        for r in records:

            if "p=reject" not in str(r):
                return 20

    except:
        pass

    return 0


import requests


def ip_reputation(ip):

    try:

        data = requests.get(
            f"https://ipapi.co/{ip}/json/"
        ).json()

        if data.get("bogon"):
            return 50

    except:
        pass

    return 0

def blacklist_score(domain, db):
    
    bad = db.blacklist.find_one({"domain": domain})

    if bad:
        return 80

    return 0

def header_score(msg):
    
    headers = str(msg)

    score = 0

    if "spf=fail" in headers:
        score += 30

    if "dkim=fail" in headers:
        score += 30

    return score

def ai_phishing(subject, body):
    
    text = (subject + body).lower()

    phishing_words = [
        "verify account",
        "bank login",
        "update payment",
        "urgent action required"
    ]

    for w in phishing_words:

        if w in text:
            return 40

    return 0


def total_security_score(subject, body, sender, attachments, msg, db):
    
    score = 0

    score += ml_spam_score(subject, body)

    score += domain_reputation(sender)

    score += domain_age_score(sender)

    score += url_reputation(body)

    score += shortlink_score(body)

    score += attachment_score(attachments)

    score += sender_behavior(sender, db)

    score += header_score(msg)

    score += ai_phishing(subject, body)

    return min(score, 100)
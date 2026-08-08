# 👑 FunStat Full Clone - With Owner Control

Telegram bot @Funstatinsfostat_bot ka full clone with **Owner Credit Management**

### ✅ Features (Sare Funstat wale)
- 🔍 **User Check** (1 Credit) - ID/Username/Forward se full report: Groups, Messages count, Name/Photo/Username history, Activity, Interests, Scam check
- 🌐 **Chat Search** (1 Credit) - Keyword se public groups/channels search
- 📝 **Word Analysis** (1 Credit) - User ke most used words + frequency graph
- 👁 **Surveillance** (1 Credit / 28 Days) - Target ko track, har change pe notification
- 📜 History, Referral, Multi-language (auto-detect)

### 💎 Owner Control (Aapne jo manga)
Bot ke andar **/owner** panel + Web Dashboard dono:

1. **Price Per Credit set karo** - Example: `₹20 = 1 credit` aap kabhi bhi change kar sakte ho
2. **UPI ID lagao** - Bot auto QR banayega, user pay karke screenshot bhejega, aap Approve karoge
3. **USDT Addresses** - TRC20 + BEP20 dono set kar sakte ho
4. **Manual Credit Add/Remove** - Kisi bhi user ko credits do
5. **Pending Payments** - UPI/USDT proofs dekho, ✅ Approve / ❌ Reject 1 click me
6. **Stats & Broadcast** - Total users, credits, spent dekho + sabko message bhejo

### 🚀 Setup (Credentials kaise lagaye)

1. **Bot Token:** @BotFather pe jao -> /newbot -> naam do -> token copy karo
2. **API ID/Hash:** https://my.telegram.org -> API Development Tools -> App banao -> API_ID & API_HASH copy
3. **Owner ID:** @userinfobot ko /start karo -> apni ID copy karo

Fir:

```bash
cp .env.example .env
nano .env  # yaha 3 cheeze bharo: BOT_TOKEN, API_ID, API_HASH, OWNER_ID
pip install -r requirements.txt
python bot.py
```

Web Panel ke liye:
```bash
python admin_web/app.py
# Open: http://localhost:5000
```

### 💳 Payment Flow (User ke liye)
1. User /start -> Buy Credits -> 5/10/25/50/100 choose
2. UPI ya USDT choose -> QR/Address dikhega + amount
3. Pay karke screenshot/hash bhejega -> Status: Pending
4. Owner ko notification -> Owner panel me Approve -> Credits auto add + user ko msg

### 📂 Structure
```
bot.py (main bot)
config.py
database/db.py
handlers/osint_engine.py (Telethon logic)
admin_web/app.py (web owner panel)
```

### ⚠️ Note
- Bot sirf **public data** use karta hai, private chats nahi dekhta (Telegram ToS safe)
- Pehle demo mode me chalega, API lagate hi real data ayega
- Aap price/UPI/USDT kabhi bhi bot ke /owner se ya web se change kar sakte ho

Ready? Apne credentials bhejo, mai deploy me help kar dunga!

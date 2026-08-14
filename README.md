# 🎬 YouTube Downloader Telegram Bot (Pyrogram)

YouTube ဗီဒီယို / အသံ ကို Telegram ကနေ တိုက်ရိုက် ဒေါင်းလုဒ်လုပ်နိုင်တဲ့ Bot။  
**Pyrogram** သုံးထားပြီး Facebook bot (`@UseMasterUpdate`) ပုံစံအတိုင်း ရေးထားပါတယ်။

## ✨ Features

- YouTube လင့်ခ် ပို့ရုံနဲ့ **Video (MP4)** / **Audio (MP3)** ရွေးချယ်နိုင်
- Live **progress bar** (download + upload)
- နာရီကျော် ဗီဒီယိုများ အတွက် အမြန်ဒေါင်းလုဒ် (`concurrent_fragment_downloads=16`)
- Pyrogram မို့ ဖိုင် **~2GB** အထိ ပို့နိုင်
- Thumbnail + duration metadata ပါ

## 📋 Requirements

- Python 3.10+
- FFmpeg
- `API_ID` + `API_HASH` (https://my.telegram.org)
- `BOT_TOKEN` (@BotFather)

## 🚀 Local Run

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd YOUR_REPO

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt

# FFmpeg
# sudo apt install ffmpeg

cp .env.example .env
# .env ထဲမှာ API_ID, API_HASH, BOT_TOKEN ထည့်ပါ

python bot.py
```

## ☁️ Deploy (Railway / Render)

1. GitHub မှာ repo တင်ပါ
2. Railway သို့မဟုတ် Render မှာ project ဖန်တီးပါ
3. Environment Variables ထည့်ပါ:

| Variable          | Required | Description                          |
|-------------------|----------|--------------------------------------|
| `API_ID`          | Yes      | from https://my.telegram.org         |
| `API_HASH`        | Yes      | from https://my.telegram.org         |
| `BOT_TOKEN`       | Yes      | from @BotFather                      |
| `MAX_FILE_SIZE_MB`| No       | default `2000` (2GB)                 |

4. Deploy

`Dockerfile` + `Procfile` + `railway.json` + `render.yaml` ပါပြီးသားမို့ auto detect လုပ်ပါလိမ့်မယ်။

## 📁 Project Structure

```
.
├── bot.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── Procfile
├── railway.json
├── render.yaml
├── .env.example
├── .gitignore
├── LICENSE
└── README.md
```

## ⚠️ Notes

- Pyrogram က MTProto သုံးတာမို့ official Bot API ထက် ဖိုင်အကြီးကြီး ပိုလွယ်ကူစွာ ပို့နိုင်ပါတယ်။
- Free plan တွေမှာ sleep ဖြစ်နိုင်ပါတယ်။
- Credit ကို `bot.py` ထဲက `CREDIT = "@YourCredit"` မှာ ပြောင်းပါ။

## 📄 License

MIT License

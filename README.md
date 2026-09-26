# Data Spoofer

Prepíš **metadata videa** (MP4/MOV): wipe starých tagov + nový fingerprint (telefón, GPS z mapy, čas).

> Menia sa len metadata kontajnera, **nie pixely**.  
> Nástroj **neodstraňuje** SynthID / AI watermarky v obraze.

## Lokálne

```bash
brew install exiftool   # + ffmpeg
pip3 install -r requirements.txt
python3 app.py
```

Otvor http://127.0.0.1:5050

## Free online hosting (Render)

Netlify toto **nevie** spustiť (treba Python + ExifTool + ffmpeg).

**Render** free tier áno (Docker):

1. Daj projekt na GitHub
2. Choď na [https://render.com](https://render.com) → Sign up (GitHub)
3. **New → Web Service** → Connect repo
4. Nastavenia:
   - **Runtime:** Docker
   - **Plan:** Free
5. Deploy → dostaneš URL typu `https://data-spoofer-xxxx.onrender.com`

Alebo ak máš `render.yaml` v repo, Render ho môže načítať automaticky (Blueprint).

### Obmedzenia free tieru

- po ~15 min nečinnosti spí (prvý request potrvá ~30–60 s)
- max upload ~200 MB (env `MAX_UPLOAD_MB`)
- veľké videá môžu timeoutnúť — skús kratšie / menšie súbory

### Alternatívy

| Služba | Poznámka |
|--------|----------|
| [Render](https://render.com) | free Docker, spí |
| [Railway](https://railway.app) | trial kredity |
| [Fly.io](https://fly.io) | free allowance + Docker |
| [Koyeb](https://www.koyeb.com) | free instance |

## Docker lokálne

```bash
docker build -t data-spoofer .
docker run --rm -p 8080:8080 -e SECRET_KEY=dev data-spoofer
```

## CLI

```bash
python3 spoof.py list
python3 spoof.py spoof video.mp4 -p iphone-15-pro -l sk-bratislava --show
```

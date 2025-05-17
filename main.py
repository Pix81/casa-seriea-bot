from flask import Flask
import threading
import feedparser
from datetime import datetime
import requests
from requests.auth import HTTPBasicAuth
from io import BytesIO
from PIL import Image
import os
from openai import OpenAI

# 🔐 Credenziali da variabili d'ambiente
import os
from openai import OpenAI
WP_USER = os.getenv("WP_USER")
WP_PASSWORD = os.getenv("WP_PASSWORD")
WP_BASE = os.getenv("WP_BASE")
client = OpenAI()


wp_url = f"{WP_BASE}/wp-json/wp/v2/posts"
wp_media_url = f"{WP_BASE}/wp-json/wp/v2/media"
tag_keywords = ["Napoli", "Inter", "Milan", "Juventus", "Atalanta", "Roma", "Fiorentina"]

def convert_png_to_jpg(image_url):
    try:
        response = requests.get(image_url)
        img = Image.open(BytesIO(response.content)).convert("RGB")
        buffer = BytesIO()
        img.save(buffer, format="JPEG")
        buffer.seek(0)
        return buffer, "immagine_seriea.jpg"
    except Exception as e:
        print("❌ Errore conversione PNG→JPG:", e)
        return None, None

def upload_image(image_url):
    try:
        print("🔁 Upload immagine:", image_url)
        img_buffer, name = convert_png_to_jpg(image_url)
        if not img_buffer:
            return None
        headers = {
            "Content-Disposition": f"attachment; filename={name}",
            "Content-Type": "image/jpeg"
        }
        r = requests.post(wp_media_url, auth=HTTPBasicAuth(WP_USER, WP_PASSWORD), headers=headers, data=img_buffer)
        print("📥 Upload status:", r.status_code)
        if r.status_code == 201:
            return r.json()["id"]
        else:
            print("❌ Upload fallito:", r.text)
    except Exception as e:
        print("❌ Errore upload immagine:", e)
    return None

def get_id(endpoint, name):
    r = requests.get(f"{WP_BASE}/wp-json/wp/v2/{endpoint}?search={name}", auth=HTTPBasicAuth(WP_USER, WP_PASSWORD))
    data = r.json()
    return data[0]["id"] if data else None

def genera_immagine_dalle(titolo):
    prompt = f"Copertina realistica per un articolo sportivo su Serie A: '{titolo}'. Visuale dallo stadio, tifosi esultanti, giocatori in azione, bandiere italiane. Atmosfera intensa e professionale."
    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1
        )
        return response.data[0].url
    except Exception as e:
        print("❌ Errore DALL·E:", e)
        return None

def genera_articoli():
    oggi = datetime.now().strftime("%d %B %Y")
    rss_url = "https://news.google.com/rss/search?q=calcio+serie+A&hl=it&gl=IT&ceid=IT:it"
    notizie = feedparser.parse(rss_url).entries[:3]

    for i, notizia in enumerate(notizie, 1):
        titolo = notizia.title
        link = notizia.link

        prompt = (
    f"Scrivi prima un titolo breve (massimo 75 caratteri) su una sola riga. "
    f"Poi vai a capo due volte e scrivi l’articolo giornalistico completo in italiano "
    f"su Serie A, basato su questa notizia: '{titolo}' ({link}). "
    f"Includi contesto, classifica, tattica, dichiarazioni, numeri e scenari. "
    f"Stile giornalistico. Data: {oggi}. Lunghezza tra 500 e 2000 parole."
)


        tentativi = 0
        content = ""

        while len(content.split()) < 300 and tentativi < 3:
            try:
                res = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.9
                )
                content = res.choices[0].message.content.strip()
            except Exception as e:
                print(f"❌ Errore OpenAI (tentativo {tentativi + 1}): {e}")
                break

            if len(content.split()) < 300:
                print(f"⚠️ Articolo troppo corto ({len(content.split())} parole). Riprovo...")
                tentativi += 1

        if len(content.split()) < 300:
            print(f"❌ Dopo {tentativi} tentativi, articolo ancora troppo corto. Skippato.")
            continue

        tags = []
        for team in tag_keywords:
            if team.lower() in content.lower():
                tag_id = get_id("tags", team)
                if tag_id:
                    tags.append(tag_id)

        cat_id = get_id("categories", "Serie A")

image_url = genera_immagine_dalle(titolo)
print("📸 Immagine:", image_url)
if not image_url:
    image_url = "https://www.casaseriea.it/wp-content/uploads/2024/01/serie-a-default.jpg"

featured_media_id = upload_image(image_url)
split_content = content.split("\n\n", 1)
titolo_breve = split_content[0][:75]
corpo_articolo = split_content[1] if len(split_content) > 1 else content

post_data = {
    "title": titolo_breve,
    "content": corpo_articolo,
    "status": "publish",
    "tags": tags,
    "categories": [cat_id] if cat_id else []
}
if featured_media_id:
    post_data["featured_media"] = featured_media_id



        r = requests.post(wp_url, auth=HTTPBasicAuth(WP_USER, WP_PASSWORD), json=post_data)
        if r.status_code == 201:
            print(f"✅ PUBBLICATO: {r.json()['link']}")
        else:
            print(f"❌ ERRORE {r.status_code}: {r.text}")

# Flask Webhook
app = Flask(__name__)

@app.route("/")
def webhook():
    threading.Thread(target=genera_articoli).start()
    return "✅ Bot Casa Serie A eseguito!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

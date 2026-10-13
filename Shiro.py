import urllib.request
import urllib.parse
import json
import time
import os
import threading
import http.server
import socketserver

# Your Telegram Bot Token
TOKEN = "8990609694:AAGzUx7nANDeFNS3BZR_skZq5uKodsX5ZO8"
TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"

user_sessions = {}

def send_message(chat_id, text):
    data = urllib.parse.urlencode({'chat_id': chat_id, 'text': text}).encode('utf-8')
    req = urllib.request.Request(f"{TELEGRAM_API}/sendMessage", data=data)
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"[-] Error sending message: {e}")

def send_photo(chat_id, photo_url, caption=""):
    data = urllib.parse.urlencode({
        'chat_id': chat_id, 
        'photo': photo_url,
        'caption': caption
    }).encode('utf-8')
    req = urllib.request.Request(f"{TELEGRAM_API}/sendPhoto", data=data)
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"[-] Error sending photo: {e}")

def search_mangadex(query):
    encoded_query = urllib.parse.quote(query)
    url = f"https://api.mangadex.org/manga?title={encoded_query}&limit=5"
    req = urllib.request.Request(url, headers={'User-Agent': 'TelegramMangaBot/1.0'})
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            results = []
            for item in data.get('data', []):
                manga_id = item['id']
                titles = item['attributes']['title']
                title = titles.get('en', list(titles.values())[0] if titles else 'Unknown')
                results.append({'id': manga_id, 'title': title})
            return results
    except Exception as e:
        print(f"[-] MangaDex API error: {e}")
        return []

def get_chapters(manga_id):
    url = f"https://api.mangadex.org/manga/{manga_id}/feed?translatedLanguage[]=en&limit=15&order[chapter]=asc"
    req = urllib.request.Request(url, headers={'User-Agent': 'TelegramMangaBot/1.0'})
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            chapters = []
            for item in data.get('data', []):
                chap_id = item['id']
                attrs = item['attributes']
                chap_num = attrs.get('chapter', '0')
                chap_title = attrs.get('title', '') or ''
                chapters.append({'id': chap_id, 'number': chap_num, 'title': chap_title})
            return chapters
    except Exception as e:
        print(f"[-] Chapters API error: {e}")
        return []

def get_chapter_pages(chapter_id):
    url = f"https://api.mangadex.org/at-home/server/{chapter_id}"
    req = urllib.request.Request(url, headers={'User-Agent': 'TelegramMangaBot/1.0'})
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            base_url = data['baseUrl']
            chapter_data = data['chapter']
            hash_val = chapter_data['hash']
            
            files = chapter_data.get('dataSaver')
            folder = 'data-saver'
            if not files:
                files = chapter_data.get('data', [])
                folder = 'data'
            
            pages = [f"{base_url}/{folder}/{hash_val}/{file}" for file in files]
            return pages
    except Exception as e:
        print(f"[-] Pages API error: {e}")
        return []

def get_updates(offset=None):
    url = f"{TELEGRAM_API}/getUpdates?timeout=30"
    if offset:
        url += f"&offset={offset}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=35) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception:
        return {'result': []}

def run_bot():
    print("[*] Telegram Manga Bot background polling started.")
    offset = None
    while True:
        updates = get_updates(offset)
        for update in updates.get('result', []):
            offset = update['update_id'] + 1
            
            if 'message' in update and 'text' in update['message']:
                chat_id = update['message']['chat']['id']
                text = update['message']['text'].strip()
                
                if chat_id not in user_sessions:
                    user_sessions[chat_id] = {'state': 'HOME', 'manga_list': [], 'chapters': []}
                
                state = user_sessions[chat_id]['state']
                
                if text == '/start':
                    user_sessions[chat_id]['state'] = 'HOME'
                    send_message(chat_id, "📖 Welcome back!\n\nSend me the name of any manga you want to read (e.g., 'Chainsaw Man' or 'Tokyo Ghoul').")
                
                elif state == 'HOME' or text.startswith('/'):
                    send_message(chat_id, f"🔍 Searching MangaDex for '{text}'...")
                    results = search_mangadex(text)
                    if results:
                        user_sessions[chat_id]['manga_list'] = results
                        user_sessions[chat_id]['state'] = 'SELECT_MANGA'
                        
                        msg = "Found these titles. Reply with the number to select one:\n\n"
                        for i, m in enumerate(results):
                            msg += f"{i+1}. {m['title']}\n"
                        send_message(chat_id, msg)
                    else:
                        send_message(chat_id, "❌ No manga found matching that name. Try another search:")
                
                elif state == 'SELECT_MANGA':
                    try:
                        idx = int(text) - 1
                        manga_list = user_sessions[chat_id]['manga_list']
                        if 0 <= idx < len(manga_list):
                            selected = manga_list[idx]
                            user_sessions[chat_id]['selected_manga'] = selected
                            
                            send_message(chat_id, f"📥 Loading chapters for *{selected['title']}*...")
                            chapters = get_chapters(selected['id'])
                            
                            if chapters:
                                user_sessions[chat_id]['chapters'] = chapters
                                user_sessions[chat_id]['state'] = 'SELECT_CHAPTER'
                                
                                msg = f"📚 *{selected['title']}* Chapters:\nReply with the chapter number:\n\n"
                                for j, c in enumerate(chapters):
                                    msg += f"{j+1}. Chapter {c['number']} {c['title']}\n"
                                send_message(chat_id, msg)
                            else:
                                send_message(chat_id, "❌ No English chapters found for this manga.")
                        else:
                            send_message(chat_id, "⚠️ Invalid number. Choose from the list.")
                    except ValueError:
                        send_message(chat_id, "⚠️ Please reply with a valid number.")
                
                elif state == 'SELECT_CHAPTER':
                    try:
                        c_idx = int(text) - 1
                        chapters = user_sessions[chat_id]['chapters']
                        if 0 <= c_idx < len(chapters):
                            chap = chapters[c_idx]
                            send_message(chat_id, f"🚀 Loading Chapter {chap['number']} pages... Please wait.")
                            
                            pages = get_chapter_pages(chap['id'])
                            if pages:
                                send_message(chat_id, f"📖 Sending Chapter {chap['number']} ({len(pages)} pages)... Enjoy reading!")
                                
                                for p_num, page_url in enumerate(pages, 1):
                                    send_photo(chat_id, page_url, caption=f"Page {p_num} / {len(pages)}")
                                    time.sleep(0.4)
                                    
                                send_message(chat_id, "✅ Chapter finished! Send another manga name to search again or /start.")
                                user_sessions[chat_id]['state'] = 'HOME'
                            else:
                                send_message(chat_id, "❌ Could not load chapter pages.")
                        else:
                            send_message(chat_id, "⚠️ Invalid chapter number.")
                    except ValueError:
                        send_message(chat_id, "⚠️ Please reply with a valid chapter number.")
                        
        time.sleep(1)

# Render requires an HTTP server listening on the dynamic $PORT environment variable
PORT = int(os.environ.get("PORT", 10000))

class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Manga Telegram Bot is online and running!")

def run_http_server():
    with socketserver.TCPServer(("0.0.0.0", PORT), HealthCheckHandler) as httpd:
        print(f"[*] HTTP health server listening on port {PORT}")
        httpd.serve_forever()

if __name__ == "__main__":
    # Start the Telegram bot polling loop in a background thread
    threading.Thread(target=run_bot, daemon=True).start()
    # Start the HTTP server on the main thread to satisfy Render's health checks
    run_http_server()

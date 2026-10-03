import html
import io
import json
import os
import re
import ssl
import threading
import time
import urllib.request
import pygame

# Безопасный импорт dotenv
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass

FOLDER_ID = os.getenv("folder_id", "")
API_KEY = os.getenv("api_key", "")

# Подключение к Yandex AI Studio (OpenAI-совместимый эндпоинт)
ai_client = None
if FOLDER_ID and API_KEY:
    try:
        from openai import OpenAI
        ai_client = OpenAI(
            base_url="https://ai.api.cloud.yandex.net/v1",
            api_key=API_KEY,
            project=FOLDER_ID,
        )
        AI_MODEL = f"gpt://{FOLDER_ID}/deepseek-v4.1-flash"
    except Exception as e:
        print(f"Клиент OpenAI не инициализирован (будет заглушка): {e}")
        ai_client = None

# Отключение строгой проверки SSL-сертификатов (для macOS)
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

# Инициализация Pygame
pygame.init()
WIDTH, HEIGHT = 1050, 720
SCREEN = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("ГМИИ им. А.С. Пушкина — Музейные AI-квесты")

# Цветовая палитра
BG_COLOR = (244, 241, 234)
WALL_COLOR = (65, 50, 42)
PLAYER_COLOR = (41, 128, 185)
ACCENT_GOLD = (212, 160, 23)
MODAL_BG = (253, 252, 248)
TEXT_DARK = (30, 30, 30)
TEXT_MUTED = (110, 110, 110)
BUTTON_BG = (235, 230, 220)
BUTTON_HOVER = (220, 205, 180)

# Цвета для AI-панели
AI_BOX_BG = (250, 248, 240)
AI_BOX_BORDER = (140, 105, 50)
AI_BADGE_BG = (52, 73, 94)
AI_SUCCESS_BG = (39, 174, 96)
AI_WRONG_BG = (192, 57, 43)

# Шрифты
FONT_TITLE = pygame.font.SysFont("Arial", 20, bold=True)
FONT_MENU_TITLE = pygame.font.SysFont("Arial", 24, bold=True)
FONT_BUTTON = pygame.font.SysFont("Arial", 15, bold=True)
FONT_UI = pygame.font.SysFont("Arial", 14, bold=True)
FONT_AUTHOR = pygame.font.SysFont("Arial", 16, bold=True)
FONT_TEXT = pygame.font.SysFont("Arial", 15)
FONT_AI_TEXT = pygame.font.SysFont("Arial", 13)
FONT_HINT = pygame.font.SysFont("Arial", 12, italic=True)
FONT_CHOOSE_BTN = pygame.font.SysFont("Arial", 12, bold=True)

BASE_SITE = "https://pushkinmuseum.art"
BUILDINGS_URL = "https://www.pushkinmuseum.art/json/buildings.json"
MASTERPIECES_URL = "https://www.pushkinmuseum.art/json/masterpieces.json"


def clean_html(text: str) -> str:
    """Удаляет html-теги и спецсимволы"""
    if not text:
        return ""
    text = html.unescape(text)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


# -------------------------------------------------------------
# ГЕНЕРАЦИЯ ЗАГАДОК ЧЕРЕЗ ИИ
# -------------------------------------------------------------
SYSTEM_INSTRUCTIONS = (
    "Ты музейный ведущий для детей 5–7 лет. Пользователь передаёт hall_id и список экспонатов зала.\n"
    "По полям описания выбери один экспонат и составь загадку из 2–3 коротких предложений для ребёнка 5–7 лет.\n\n"
    "Правила:\n"
    "• Используй только видимые детали, явно описанные в данных.\n"
    "• Не придумывай цвета, предметы, действия и другие признаки.\n"
    "• Не раскрывай название экспоната и имя автора.\n"
    "• Не требуй знания дат, истории или сложных терминов.\n"
    "• Загадка должна подходить только одному экспонату из выбранного списка.\n\n"
    "Стиль загадки:\n"
    "• Игровая форма: «кто я? / что я?», обращение к ребёнку или загадочный вопрос.\n"
    "• Не перечисляй предметы подряд сухим списком — подавай как намёки.\n"
    "• Ответ должен приходить в момент разгадки, а не быть очевиден сразу.\n\n"
    "Верни ТОЛЬКО валидный JSON без markdown-кавычек:\n"
    '{"hall_id":"ID зала","riddle":"Текст загадки","answer_id":"id экспоната","answer_name":"название","error":null}'
)


def request_ai_riddle(hall_id: str, exhibits: list[dict], callback):
    """
    Асинхронный вызов LLM по API.
    callback(riddle_text, answer_id, answer_name)
    """
    def _worker():
        if ai_client:
            try:
                prompt_input = json.dumps({
                    "hall_id": hall_id,
                    "exhibits": [
                        {
                            "id": ex.get("id"),
                            "name": ex.get("title"),
                            "type": ex.get("material", "Экспонат"),
                            "description": ex.get("desc")
                        }
                        for ex in exhibits
                    ]
                }, ensure_ascii=False)

                response = ai_client.responses.create(
                    model=AI_MODEL,
                    instructions=SYSTEM_INSTRUCTIONS,
                    input=prompt_input,
                )

                raw_text = response.output_text.strip()
                raw_text = re.sub(r"^```json\s*", "", raw_text)
                raw_text = re.sub(r"\s*```$", "", raw_text)

                data = json.loads(raw_text)
                if not data.get("error") and data.get("riddle"):
                    callback(data.get("riddle"), str(data.get("answer_id")), data.get("answer_name"))
                    return
            except Exception as e:
                print(f"[Yandex AI] Ошибка API, переход на заглушку: {e}")

        # Фолбек-заглушка
        import random
        time.sleep(1.0)
        target = random.choice(exhibits) if exhibits else None
        if target:
            short_desc = target["desc"][:100]
            fallback_riddle = (
                f"Я нахожусь в этом зале, и обо мне говорят так: «{short_desc}…». "
                f"Внимательно осмотри витрины вокруг и отгадай, кто я!"
            )
            callback(fallback_riddle, str(target.get("id")), target.get("title"))
        else:
            callback("В этом зале пока нет шедевров для квеста.", None, None)

    threading.Thread(target=_worker, daemon=True).start()


class Exhibit:
    """Экспонат с превью на стенде, кликом и кнопкой выбора ответа"""
    def __init__(self, x, y, data):
        self.rect = pygame.Rect(x, y, 90, 90)
        self.trigger_zone = self.rect.inflate(50, 50)
        self.choose_btn_rect = pygame.Rect(x - 5, y + 115, 100, 26)

        self.id = str(data.get("id", ""))
        self.title = data.get("title", "Без названия")
        self.author = data.get("author", "Неизвестный мастер")
        self.period = data.get("period", "")
        self.material = data.get("material", "")
        self.desc = data.get("desc", "")
        self.image_url = data.get("image_url", None)

        self.thumb_surf = None
        self.modal_surf = None
        self.loading = False

        if self.image_url:
            self.start_download()

    def start_download(self):
        if self.loading or self.thumb_surf:
            return
        self.loading = True

        def _worker():
            try:
                req = urllib.request.Request(
                    self.image_url,
                    headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
                )
                with urllib.request.urlopen(req, timeout=8, context=SSL_CTX) as resp:
                    raw_data = resp.read()

                orig = pygame.image.load(io.BytesIO(raw_data))
                ow, oh = orig.get_size()

                t_scale = min(82 / ow, 82 / oh)
                self.thumb_surf = pygame.transform.smoothscale(orig, (int(ow * t_scale), int(oh * t_scale)))

                m_scale = min(250 / ow, 270 / oh)
                self.modal_surf = pygame.transform.smoothscale(orig, (int(ow * m_scale), int(oh * m_scale)))
            except Exception:
                pass
            finally:
                self.loading = False

        threading.Thread(target=_worker, daemon=True).start()

    def draw(self, surface, mouse_pos):
        is_hover = self.rect.collidepoint(mouse_pos)
        pygame.draw.rect(surface, (235, 230, 220) if is_hover else (222, 217, 207), self.rect, border_radius=6)
        pygame.draw.rect(surface, ACCENT_GOLD if is_hover else (160, 130, 80), self.rect, width=2, border_radius=6)

        if self.thumb_surf:
            surface.blit(self.thumb_surf, self.thumb_surf.get_rect(center=self.rect.center))
        elif self.loading:
            lbl = FONT_HINT.render("Загрузка...", True, TEXT_MUTED)
            surface.blit(lbl, lbl.get_rect(center=self.rect.center))

        short_title = self.title if len(self.title) <= 15 else self.title[:14] + "…"
        lbl = FONT_HINT.render(short_title, True, TEXT_MUTED)
        surface.blit(lbl, (self.rect.centerx - lbl.get_width() // 2, self.rect.bottom + 5))

        btn_hover = self.choose_btn_rect.collidepoint(mouse_pos)
        btn_bg = (210, 195, 160) if btn_hover else (230, 225, 215)
        pygame.draw.rect(surface, btn_bg, self.choose_btn_rect, border_radius=4)
        pygame.draw.rect(surface, ACCENT_GOLD if btn_hover else (150, 140, 130), self.choose_btn_rect, width=1, border_radius=4)
        btn_text = FONT_CHOOSE_BTN.render("✓ Это ответ", True, TEXT_DARK)
        surface.blit(btn_text, btn_text.get_rect(center=self.choose_btn_rect.center))


class Player:
    def __init__(self, x, y):
        self.rect = pygame.Rect(x, y, 26, 26)
        self.speed = 5

    def move(self):
        keys = pygame.key.get_pressed()
        dx, dy = 0, 0

        left = keys[pygame.K_LEFT] or keys[pygame.KSCAN_A] or keys[pygame.K_a]
        right = keys[pygame.K_RIGHT] or keys[pygame.KSCAN_D] or keys[pygame.K_d]
        up = keys[pygame.K_UP] or keys[pygame.KSCAN_W] or keys[pygame.K_w]
        down = keys[pygame.K_DOWN] or keys[pygame.KSCAN_S] or keys[pygame.K_s]

        if left:
            dx -= self.speed
        if right:
            dx += self.speed
        if up:
            dy -= self.speed
        if down:
            dy += self.speed

        self.rect.x = max(20, min(WIDTH - 20 - self.rect.width, self.rect.x + dx))
        self.rect.y = max(65, min(HEIGHT - 25 - self.rect.height, self.rect.y + dy))

    def draw(self, surface):
        pygame.draw.circle(surface, PLAYER_COLOR, self.rect.center, self.rect.width // 2)
        pygame.draw.circle(surface, (255, 255, 255), self.rect.center, self.rect.width // 2, 2)


class AIQuestBox:
    def __init__(self, x, y, width=340, height=155):
        self.rect = pygame.Rect(x, y, width, height)
        self.close_btn_rect = pygame.Rect(self.rect.right - 28, self.rect.top + 6, 22, 22)
        self.reopen_btn_rect = pygame.Rect(WIDTH - 160, HEIGHT - 45, 140, 32)
        
        self.riddle = None
        self.target_id = None
        self.target_name = None
        self.is_solved = False
        self.wrong_feedback = False
        self.feedback_timer = 0
        self.is_loading = True
        self.is_minimized = False

    def reset(self):
        self.riddle = None
        self.target_id = None
        self.target_name = None
        self.is_solved = False
        self.wrong_feedback = False
        self.feedback_timer = 0
        self.is_loading = True
        self.is_minimized = False

    def on_ai_response(self, riddle, target_id, target_name):
        self.riddle = riddle
        self.target_id = str(target_id) if target_id else None
        self.target_name = target_name
        self.is_loading = False

    def check_guess(self, chosen_exhibit: Exhibit):
        if self.is_solved or not self.target_id:
            return

        is_match = (
            (self.target_id and self.target_id == chosen_exhibit.id) or
            (self.target_name and self.target_name.lower() in chosen_exhibit.title.lower()) or
            (chosen_exhibit.title.lower() in (self.target_name or "").lower())
        )

        if is_match:
            self.is_solved = True
            self.wrong_feedback = False
        else:
            self.wrong_feedback = True
            self.feedback_timer = time.time() + 2.5

    def draw(self, surface, mouse_pos):
        if self.is_minimized:
            is_hover = self.reopen_btn_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surface, BUTTON_HOVER if is_hover else BUTTON_BG, self.reopen_btn_rect, border_radius=6)
            pygame.draw.rect(surface, ACCENT_GOLD, self.reopen_btn_rect, width=2, border_radius=6)
            txt = FONT_HINT.render("✨ Загадка от ИИ", True, TEXT_DARK)
            surface.blit(txt, txt.get_rect(center=self.reopen_btn_rect.center))
            return

        if self.wrong_feedback and time.time() > self.feedback_timer:
            self.wrong_feedback = False

        pygame.draw.rect(surface, AI_BOX_BG, self.rect, border_radius=10)
        border_col = AI_SUCCESS_BG if self.is_solved else (AI_WRONG_BG if self.wrong_feedback else AI_BOX_BORDER)
        pygame.draw.rect(surface, border_col, self.rect, width=2, border_radius=10)

        badge_rect = pygame.Rect(self.rect.x + 12, self.rect.y + 10, 140, 22)
        if self.is_solved:
            badge_col = AI_SUCCESS_BG
            badge_text = "🎉 РАЗГАДАНО!"
        elif self.wrong_feedback:
            badge_col = AI_WRONG_BG
            badge_text = "❌ НЕ ОНО"
        else:
            badge_col = AI_BADGE_BG
            badge_text = "🤖 Загадка от ИИ"

        pygame.draw.rect(surface, badge_col, badge_rect, border_radius=5)
        badge_lbl = FONT_HINT.render(badge_text, True, (255, 255, 255))
        surface.blit(badge_lbl, (badge_rect.x + 8, badge_rect.y + 3))

        is_close_hover = self.close_btn_rect.collidepoint(mouse_pos)
        pygame.draw.rect(surface, (215, 205, 195) if is_close_hover else (235, 225, 215), self.close_btn_rect, border_radius=4)
        x_lbl = FONT_HINT.render("✕", True, TEXT_DARK)
        surface.blit(x_lbl, x_lbl.get_rect(center=self.close_btn_rect.center))

        if self.is_loading:
            loading_txt = FONT_HINT.render("ИИ придумывает загадку по залу...", True, TEXT_MUTED)
            surface.blit(loading_txt, (self.rect.x + 14, self.rect.y + 55))
        elif self.is_solved:
            solved_txt = f"Верно! Вы нашли шедевр «{self.target_name}»! Нажмите на него, чтобы узнать больше."
            render_wrapped_text(surface, solved_txt, self.rect.x + 14, self.rect.y + 45, self.rect.width - 28, max_lines=4, font=FONT_AI_TEXT)
        elif self.wrong_feedback:
            wrong_txt = "Это не тот экспонат! Внимательно прочтите намёки в загадке и попробуйте другой."
            render_wrapped_text(surface, wrong_txt, self.rect.x + 14, self.rect.y + 45, self.rect.width - 28, max_lines=4, font=FONT_AI_TEXT)
        elif self.riddle:
            render_wrapped_text(surface, self.riddle, self.rect.x + 14, self.rect.y + 40, self.rect.width - 28, max_lines=5, font=FONT_AI_TEXT)


def render_wrapped_text(surface, text, x, y, max_w, max_lines=8, line_spacing=4, font=FONT_TEXT):
    words = text.split(" ")
    lines = []
    curr_line = []

    for word in words:
        test = " ".join(curr_line + [word])
        if font.size(test)[0] < max_w:
            curr_line.append(word)
        else:
            lines.append(" ".join(curr_line))
            curr_line = [word]
            if len(lines) >= max_lines:
                break

    if curr_line and len(lines) < max_lines:
        lines.append(" ".join(curr_line))

    if len(lines) == max_lines:
        lines[-1] = lines[-1].rstrip("., ") + "…"

    curr_y = y
    for line in lines:
        rendered = font.render(line, True, TEXT_DARK)
        surface.blit(rendered, (x, curr_y))
        curr_y += font.size(line)[1] + line_spacing


def draw_modal(surface, exhibit: Exhibit, hall_title: str):
    dim = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    dim.fill((0, 0, 0, 160))
    surface.blit(dim, (0, 0))

    m_w, m_h = 780, 430
    m_x, m_y = (WIDTH - m_w) // 2, (HEIGHT - m_h) // 2
    modal_rect = pygame.Rect(m_x, m_y, m_w, m_h)

    pygame.draw.rect(surface, MODAL_BG, modal_rect, border_radius=12)
    pygame.draw.rect(surface, ACCENT_GOLD, modal_rect, width=3, border_radius=12)

    img_box = pygame.Rect(m_x + 25, m_y + 25, 250, 270)
    pygame.draw.rect(surface, (230, 226, 218), img_box, border_radius=8)

    if exhibit.modal_surf:
        surface.blit(exhibit.modal_surf, exhibit.modal_surf.get_rect(center=img_box.center))
    else:
        status_lbl = FONT_HINT.render("Загрузка..." if exhibit.loading else "Нет фото", True, TEXT_MUTED)
        surface.blit(status_lbl, status_lbl.get_rect(center=img_box.center))

    cx = m_x + 295
    cw = m_w - 320

    surface.blit(FONT_TITLE.render(exhibit.title, True, (150, 35, 35)), (cx, m_y + 25))

    author_str = exhibit.author if exhibit.author else "Мастер неизвестен"
    if exhibit.period:
        author_str += f" ({exhibit.period})"
    surface.blit(FONT_AUTHOR.render(author_str, True, (60, 60, 60)), (cx, m_y + 55))

    surface.blit(FONT_HINT.render(hall_title, True, (130, 90, 40)), (cx, m_y + 78))

    pygame.draw.line(surface, (215, 208, 195), (cx, m_y + 102), (m_x + m_w - 25, m_y + 102), 1)
    render_wrapped_text(surface, exhibit.desc, cx, m_y + 115, cw, max_lines=9)

    surface.blit(FONT_HINT.render("[ESC] или [E] — закрыть", True, (130, 130, 130)), (m_x + 25, m_y + m_h - 35))


def load_all_museum_data():
    """
    Скачивает buildings.json и masterpieces.json напрямую по сети,
    динамически разбирает структуру и связывает залы с экспонатами.
    """
    # 1. Загрузка структуры зданий и залов из сети
    print("Загрузка структуры зданий из сети...")
    req_b = urllib.request.Request(BUILDINGS_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req_b, timeout=15, context=SSL_CTX) as resp:
        buildings_raw = json.loads(resp.read().decode("utf-8"))

    halls_meta = {}
    database = {}

    target_building_ids = ("116", "117")
    for b_id in target_building_ids:
        b_info = buildings_raw.get(b_id, {})
        b_name = b_info.get("name", {}).get("ru", f"Здание {b_id}")
        b_brief = clean_html(b_info.get("brief", {}).get("ru", ""))

        database[b_id] = {
            "name": b_name,
            "desc": b_brief,
            "halls": {}
        }

        # Разбор этажей и залов
        floors = b_info.get("floors", {})
        if isinstance(floors, dict):
            for f_info in floors.values():
                halls = f_info.get("halls", {})
                if isinstance(halls, dict):
                    for h_id, h_info in halls.items():
                        h_name = h_info.get("name", {}).get("ru", f"Зал {h_id}")
                        h_num = h_info.get("number", "")
                        hall_title = f"Зал {h_num}: {h_name}" if h_num else h_name
                        halls_meta[str(h_id)] = {
                            "building_id": b_id,
                            "title": hall_title
                        }

    # Маппинг ключевых слов художников для Галереи 117 (где поле hall в каталоге пустое)
    name_to_hall_id = {}
    for h_id, meta in halls_meta.items():
        if meta["building_id"] == "117":
            words = re.findall(r"[А-Яа-яA-Za-z]+", meta["title"])
            for word in words:
                w_low = word.lower()
                if len(w_low) > 3 and w_low not in ("зал", "искусство", "школа", "века", "стран"):
                    name_to_hall_id[w_low[:5]] = h_id

    # 2. Загрузка шедевров из сети
    print("Загрузка каталога шедевров из сети...")
    req_m = urllib.request.Request(MASTERPIECES_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req_m, timeout=15, context=SSL_CTX) as resp:
        catalog = json.loads(resp.read().decode("utf-8"))

    # 3. Фильтрация и связывание шедевров
    for exhibit_id, item in catalog.items():
        desc = clean_html(item.get("text", {}).get("ru", ""))
        annot = clean_html(item.get("annotation", {}).get("ru", ""))
        full_desc = desc if desc else annot

        # Исключаем экспонаты без текста описания
        if not full_desc or len(full_desc) < 30:
            continue

        raw_b_id = str(item.get("building", "")).strip()
        raw_hall_id = str(item.get("hall", "")).strip()

        author = ""
        authors_dict = item.get("authors")
        if isinstance(authors_dict, dict) and authors_dict:
            first_author = next(iter(authors_dict.values()))
            author = first_author.get("ru", "")

        b_id = None
        hall_id = raw_hall_id

        # Определение здания и зала
        if hall_id in halls_meta:
            b_id = halls_meta[hall_id]["building_id"]
        elif raw_b_id == "117" and author:
            auth_lower = author.lower()
            for key_prefix, target_h_id in name_to_hall_id.items():
                if key_prefix in auth_lower:
                    hall_id = target_h_id
                    b_id = "117"
                    break

        if not b_id or b_id not in database or not hall_id:
            continue

        title = item.get("name", {}).get("ru", "Экспонат")
        period = item.get("period", {}).get("text", {}).get("ru", "")
        material = item.get("material", {}).get("ru", "")

        img_url = None
        gallery = item.get("gallery", {})
        if isinstance(gallery, dict) and gallery:
            first_slot = next(iter(gallery.values()))
            path = first_slot.get("id01")
            if path:
                img_url = f"{BASE_SITE}{path}"

        hall_title = halls_meta.get(hall_id, {}).get("title", f"Зал №{hall_id}")

        if hall_id not in database[b_id]["halls"]:
            database[b_id]["halls"][hall_id] = {
                "title": hall_title,
                "items": []
            }

        database[b_id]["halls"][hall_id]["items"].append({
            "id": exhibit_id,
            "title": title,
            "author": author,
            "period": period,
            "material": material,
            "desc": full_desc,
            "image_url": img_url,
        })

    return database


def main():
    clock = pygame.time.Clock()

    try:
        museum_db = load_all_museum_data()
    except Exception as e:
        print(f"Ошибка загрузки данных: {e}")
        return

    state = "SELECT_BUILDING"
    selected_building_id = None
    selected_hall_id = None
    current_exhibits = []
    player = Player(WIDTH // 2, HEIGHT - 100)

    ai_quest_box = AIQuestBox(WIDTH - 360, HEIGHT - 180, width=340, height=155)

    coords = [
        (160, 140), (455, 140), (750, 140),
        (160, 390), (455, 390), (750, 390)
    ]

    show_modal = False
    active_exhibit = None

    building_buttons = [
        {
            "id": "116",
            "rect": pygame.Rect(100, 150, 850, 200),
            "title": "🏛️ " + museum_db["116"]["name"],
            "desc": museum_db["116"]["desc"],
            "badge": f"{len(museum_db['116']['halls'])} залов с шедеврами"
        },
        {
            "id": "117",
            "rect": pygame.Rect(100, 390, 850, 200),
            "title": "🎨 " + museum_db["117"]["name"],
            "desc": museum_db["117"]["desc"],
            "badge": f"{len(museum_db['117']['halls'])} залов с шедеврами"
        }
    ]

    hall_buttons = []

    def update_hall_buttons(b_id):
        nonlocal hall_buttons
        hall_buttons = []
        halls = museum_db[b_id]["halls"]
        btn_w, btn_h = 450, 52
        start_y = 115

        for i, (h_id, h_data) in enumerate(halls.items()):
            col = i % 2
            row = i // 2
            bx = 60 + col * (btn_w + 30)
            by = start_y + row * (btn_h + 16)
            label = f"{h_data['title']} ({len(h_data['items'])} экcп.)"
            hall_buttons.append({
                "id": h_id,
                "rect": pygame.Rect(bx, by, btn_w, btn_h),
                "label": label
            })

    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if state == "SELECT_BUILDING":
                    for btn in building_buttons:
                        if btn["rect"].collidepoint(event.pos):
                            selected_building_id = btn["id"]
                            update_hall_buttons(selected_building_id)
                            state = "SELECT_HALL"
                            break

                elif state == "SELECT_HALL":
                    back_btn = pygame.Rect(30, 20, 190, 36)
                    if back_btn.collidepoint(event.pos):
                        state = "SELECT_BUILDING"
                    else:
                        for btn in hall_buttons:
                            if btn["rect"].collidepoint(event.pos):
                                selected_hall_id = btn["id"]
                                hall_obj = museum_db[selected_building_id]["halls"][selected_hall_id]
                                items = hall_obj["items"][:6]
                                current_exhibits = [Exhibit(x, y, data) for (x, y), data in zip(coords, items)]
                                player.rect.x = WIDTH // 2
                                player.rect.y = HEIGHT - 100
                                state = "ROOM"

                                ai_quest_box.reset()
                                request_ai_riddle(selected_hall_id, items, ai_quest_box.on_ai_response)
                                break

                elif state == "ROOM" and not show_modal:
                    back_btn = pygame.Rect(20, 16, 180, 36)
                    if back_btn.collidepoint(event.pos):
                        state = "SELECT_HALL"
                    elif not ai_quest_box.is_minimized and ai_quest_box.close_btn_rect.collidepoint(event.pos):
                        ai_quest_box.is_minimized = True
                    elif ai_quest_box.is_minimized and ai_quest_box.reopen_btn_rect.collidepoint(event.pos):
                        ai_quest_box.is_minimized = False
                    else:
                        for exh in current_exhibits:
                            if exh.choose_btn_rect.collidepoint(event.pos):
                                ai_quest_box.check_guess(exh)
                                break
                            elif exh.rect.collidepoint(event.pos):
                                active_exhibit = exh
                                show_modal = True
                                break

            elif event.type == pygame.KEYDOWN:
                if state == "ROOM":
                    is_action = (event.key in (pygame.K_e, pygame.K_SPACE) or event.scancode == pygame.KSCAN_E)
                    if is_action:
                        if show_modal:
                            show_modal = False
                        elif active_exhibit:
                            show_modal = True
                            ai_quest_box.check_guess(active_exhibit)
                    elif event.key == pygame.K_ESCAPE:
                        if show_modal:
                            show_modal = False
                        else:
                            state = "SELECT_HALL"
                elif state == "SELECT_HALL" and event.key == pygame.K_ESCAPE:
                    state = "SELECT_BUILDING"

        SCREEN.fill(BG_COLOR)

        # 1. ЭКРАН ВЫБОРА ЗДАНИЯ
        if state == "SELECT_BUILDING":
            title = FONT_MENU_TITLE.render("Государственный музей изобразительных искусств им. А.С. Пушкина", True, WALL_COLOR)
            subtitle = FONT_TEXT.render("Выберите корпус для начала квеста-экскурсии:", True, TEXT_MUTED)
            SCREEN.blit(title, (WIDTH // 2 - title.get_width() // 2, 45))
            SCREEN.blit(subtitle, (WIDTH // 2 - subtitle.get_width() // 2, 85))

            for btn in building_buttons:
                is_hover = btn["rect"].collidepoint(mouse_pos)
                bg = BUTTON_HOVER if is_hover else BUTTON_BG
                pygame.draw.rect(SCREEN, bg, btn["rect"], border_radius=12)
                pygame.draw.rect(SCREEN, ACCENT_GOLD if is_hover else (180, 175, 165), btn["rect"], width=3, border_radius=12)

                t_surf = FONT_MENU_TITLE.render(btn["title"], True, TEXT_DARK)
                d_surf = FONT_TEXT.render(btn["desc"][:85] + ("…" if len(btn["desc"]) > 85 else ""), True, TEXT_MUTED)
                b_surf = FONT_UI.render(btn["badge"], True, (130, 90, 40))

                SCREEN.blit(t_surf, (btn["rect"].x + 30, btn["rect"].y + 35))
                SCREEN.blit(d_surf, (btn["rect"].x + 30, btn["rect"].y + 85))
                SCREEN.blit(b_surf, (btn["rect"].x + 30, btn["rect"].y + 135))

        # 2. ЭКРАН ВЫБОРА ЗАЛОВ
        elif state == "SELECT_HALL":
            back_btn = pygame.Rect(30, 20, 190, 36)
            is_back_hover = back_btn.collidepoint(mouse_pos)
            pygame.draw.rect(SCREEN, BUTTON_HOVER if is_back_hover else BUTTON_BG, back_btn, border_radius=6)
            pygame.draw.rect(SCREEN, ACCENT_GOLD if is_back_hover else (180, 175, 165), back_btn, width=2, border_radius=6)
            SCREEN.blit(FONT_UI.render("← К зданиям (ESC)", True, TEXT_DARK), (back_btn.x + 22, back_btn.y + 10))

            b_name = museum_db[selected_building_id]["name"].split("(")[0].strip()
            header = FONT_MENU_TITLE.render(f"Залы: {b_name}", True, WALL_COLOR)
            SCREEN.blit(header, (WIDTH // 2 - header.get_width() // 2 + 50, 24))

            for btn in hall_buttons:
                is_hover = btn["rect"].collidepoint(mouse_pos)
                bg = BUTTON_HOVER if is_hover else BUTTON_BG
                pygame.draw.rect(SCREEN, bg, btn["rect"], border_radius=8)
                pygame.draw.rect(SCREEN, ACCENT_GOLD if is_hover else (180, 175, 165), btn["rect"], width=2, border_radius=8)

                text = btn["label"]
                if FONT_BUTTON.size(text)[0] > btn["rect"].width - 20:
                    text = text[:38] + "…)"
                txt_surf = FONT_BUTTON.render(text, True, TEXT_DARK)
                SCREEN.blit(txt_surf, txt_surf.get_rect(center=btn["rect"].center))

        # 3. ЭКРАН ВНУТРИ ЗАЛА
        elif state == "ROOM":
            if not show_modal:
                player.move()

            nearby_exhibit = None
            for exh in current_exhibits:
                if exh.trigger_zone.colliderect(player.rect):
                    nearby_exhibit = exh
                    break

            if not show_modal:
                active_exhibit = nearby_exhibit

            pygame.draw.rect(SCREEN, WALL_COLOR, (14, 60, WIDTH - 28, HEIGHT - 74), width=3)

            back_btn = pygame.Rect(20, 16, 180, 36)
            is_back_hover = back_btn.collidepoint(mouse_pos)
            pygame.draw.rect(SCREEN, BUTTON_HOVER if is_back_hover else BUTTON_BG, back_btn, border_radius=6)
            pygame.draw.rect(SCREEN, ACCENT_GOLD if is_back_hover else (180, 175, 165), back_btn, width=2, border_radius=6)
            back_txt = FONT_UI.render("← К залам (ESC)", True, TEXT_DARK)
            SCREEN.blit(back_txt, back_txt.get_rect(center=back_btn.center))

            b_name = museum_db[selected_building_id]["name"].split("(")[0].strip()
            h_name = museum_db[selected_building_id]["halls"][selected_hall_id]["title"]
            header_text = f"{b_name} • {h_name}"
            header_surf = FONT_TITLE.render(header_text, True, WALL_COLOR)
            SCREEN.blit(header_surf, (WIDTH // 2 - header_surf.get_width() // 2 + 50, 22))

            for exh in current_exhibits:
                exh.draw(SCREEN, mouse_pos)

            player.draw(SCREEN)

            ai_quest_box.draw(SCREEN, mouse_pos)

            if active_exhibit and not show_modal:
                hint = FONT_HINT.render("Нажмите [E], [Пробел] или кликните мышкой по экспонату для осмотра", True, (170, 40, 40))
                SCREEN.blit(hint, (WIDTH // 2 - hint.get_width() // 2, HEIGHT - 35))

            if show_modal and active_exhibit:
                draw_modal(SCREEN, active_exhibit, header_text)

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
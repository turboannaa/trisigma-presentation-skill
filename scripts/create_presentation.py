"""
Создаёт презентацию Trisigma по plan.json, используя шаблон из Google Slides.
Использование: python3 create_presentation.py plan.json
"""

import sys
import json
import math
from collections import Counter, defaultdict
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = [
    'https://www.googleapis.com/auth/presentations',
    'https://www.googleapis.com/auth/drive'
]

TEMPLATE_ID = '1r3JViMJ_gH-OGTBb4U1ijwDDvR14ulvYF4lVAckf5n0'

# Слайды с иконками (не удаляются если нужны иконки)
ICON_SLIDE_IDS = {'g3c3ed77914d_1_1168', 'g3cb6dc1957f_1_56'}

# Каталог иконок: имя → element_id на слайде иконок
# Все иконки находятся на слайде g3c3ed77914d_1_1168 (слайд 29 шаблона)
ICON_CATALOG = {
    # Люди
    "person-light":          "g3cb6dc1957f_1_18",
    "person-medium":         "g3cb6dc1957f_1_20",
    "persons-group":         "g3cb6dc1957f_1_19",
    # Стрелки
    "arrow-triangle":        "g3cb6dc1957f_1_8",
    "arrow-chevron":         "g3cb6dc1957f_1_9",
    "arrow-double-triangle": "g3cb6dc1957f_1_21",
    "arrow-chevron-large":   "g3cb6dc1957f_1_22",
    "arrow-right-filled":    "g3cb6dc1957f_1_7",
    "arrow-both-directions": "g3cb6dc1957f_1_6",
    # Ноутбуки
    "laptop-light":          "g3cb6dc1957f_1_23",
    "laptop-medium":         "g3cb6dc1957f_1_24",
    "laptop-dark":           "g3cb6dc1957f_1_0",
    # Цифры (стиль 1 — крупные градиентные)
    "number-1":              "g3cb6dc1957f_1_1",
    "number-2":              "g3cb6dc1957f_1_2",
    "number-3":              "g3cb6dc1957f_1_3",
    "number-4":              "g3cb6dc1957f_1_4",
    "number-5":              "g3cb6dc1957f_1_5",
    # Цифры (стиль 2 — компактные)
    "number-1-alt":          "g3cb6dc1957f_1_10",
    "number-2-alt":          "g3cb6dc1957f_1_11",
    "number-3-alt":          "g3cb6dc1957f_1_12",
    "number-4-alt":          "g3cb6dc1957f_1_13",
    "number-5-alt":          "g3cb6dc1957f_1_14",
    # Кружки
    "circle-filled-dark":    "g3cb6dc1957f_1_15",
    "circle-filled-medium":  "g3cb6dc1957f_1_16",
    "circle-outline":        "g3cb6dc1957f_1_17",
}

CM_TO_EMU = 914400 / 2.54


def copy_template(drive_service, title: str) -> str:
    try:
        copy = drive_service.files().copy(
            fileId=TEMPLATE_ID,
            body={"name": title}
        ).execute()
        return copy['id']
    except Exception as e:
        if '404' in str(e) or 'notFound' in str(e):
            print("\nОшибка: шаблон не найден.")
            print(f"Убедись, что у тебя есть доступ к шаблону: "
                  f"https://docs.google.com/presentation/d/{TEMPLATE_ID}")
        elif '403' in str(e):
            print("\nОшибка: нет прав на копирование шаблона.")
            print("Убедись, что прошла авторизация: python3 scripts/auth.py")
        else:
            print(f"\nОшибка при копировании шаблона: {e}")
        raise


def get_presentation(slides_service, presentation_id: str) -> dict:
    return slides_service.presentations().get(
        presentationId=presentation_id
    ).execute()


def duplicate_slide(slides_service, presentation_id: str,
                    slide_id: str, suffix: str) -> tuple[str, dict]:
    """
    Дублирует слайд и возвращает (новый_slide_id, маппинг старых element_id -> новых).
    """
    pres = get_presentation(slides_service, presentation_id)
    orig_slide = next((s for s in pres['slides'] if s['objectId'] == slide_id), None)
    if not orig_slide:
        raise ValueError(f"Слайд {slide_id} не найден")

    elem_ids = [el['objectId'] for el in orig_slide.get('pageElements', [])]
    id_map = {slide_id: f"{slide_id}_{suffix}"}
    for eid in elem_ids:
        id_map[eid] = f"{eid}_{suffix}"

    slides_service.presentations().batchUpdate(
        presentationId=presentation_id,
        body={'requests': [{'duplicateObject': {'objectId': slide_id, 'objectIds': id_map}}]}
    ).execute()

    elem_map = {eid: f"{eid}_{suffix}" for eid in elem_ids}
    return f"{slide_id}_{suffix}", elem_map


def prepare_slides(slides_service, presentation_id: str, plan_slides: list) -> list:
    """
    Для каждого слайда в плане готовит (slide_id, element_id_map).
    Если один template_id используется несколько раз — дублирует слайд.
    """
    need_count = Counter(s['template_id'] for s in plan_slides)

    available = {}
    for template_id, count in need_count.items():
        instances = [(template_id, {})]
        for i in range(1, count):
            new_sid, elem_map = duplicate_slide(
                slides_service, presentation_id, template_id, f"dup{i}"
            )
            instances.append((new_sid, elem_map))
        available[template_id] = instances

    counters = defaultdict(int)
    result = []
    for slide in plan_slides:
        tid = slide['template_id']
        idx = counters[tid]
        slide_id, elem_map = available[tid][idx]
        counters[tid] += 1
        result.append((slide, slide_id, elem_map))

    return result


def delete_unused_slides(slides_service, presentation_id: str,
                         keep_ids: set, needs_icons: bool):
    pres = get_presentation(slides_service, presentation_id)
    all_ids = [s['objectId'] for s in pres['slides']]

    # Слайды с иконками удаляем в конце (после place_icons),
    # если иконки нужны — оставляем их пока живыми
    protected = ICON_SLIDE_IDS if needs_icons else set()
    to_delete = [sid for sid in all_ids if sid not in keep_ids and sid not in protected]
    if not to_delete:
        return
    requests = [{"deleteObject": {"objectId": oid}} for oid in to_delete]
    slides_service.presentations().batchUpdate(
        presentationId=presentation_id,
        body={"requests": requests}
    ).execute()


def delete_icon_slides(slides_service, presentation_id: str):
    """Удаляет слайды с иконками после того, как все иконки размещены."""
    pres = get_presentation(slides_service, presentation_id)
    all_ids = {s['objectId'] for s in pres['slides']}
    to_delete = [sid for sid in ICON_SLIDE_IDS if sid in all_ids]
    if not to_delete:
        return
    requests = [{"deleteObject": {"objectId": oid}} for oid in to_delete]
    slides_service.presentations().batchUpdate(
        presentationId=presentation_id,
        body={"requests": requests}
    ).execute()


def reorder_slides(slides_service, presentation_id: str, ordered_ids: list[str]):
    """Переставляет слайды в нужный порядок."""
    for target_index, slide_id in enumerate(ordered_ids):
        slides_service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={'requests': [{'updateSlidesPosition': {
                'slideObjectIds': [slide_id],
                'insertionIndex': target_index
            }}]}
        ).execute()


def place_icons(slides_service, presentation_id: str, slide_assignments: list):
    """
    Размещает иконки из каталога на целевых слайдах.

    Формат в plan.json:
        "icons": [
          {
            "name": "person-light",   // имя из ICON_CATALOG
            "x_cm": 5.0,              // позиция X в сантиметрах
            "y_cm": 3.0,              // позиция Y в сантиметрах
            "width_cm": 2.0,          // опционально, по умолчанию — размер иконки из шаблона
            "height_cm": 2.0          // опционально
          }
        ]
    """
    # Проверяем есть ли вообще иконки в плане
    has_icons = any(plan_slide.get('icons') for plan_slide, _, _ in slide_assignments)
    if not has_icons:
        return

    # Читаем contentUrl всех иконок из слайда иконок в текущей презентации
    pres = get_presentation(slides_service, presentation_id)
    icon_elements = {}
    for slide in pres['slides']:
        if slide['objectId'] not in ICON_SLIDE_IDS:
            continue
        for el in slide.get('pageElements', []):
            if 'image' in el:
                icon_elements[el['objectId']] = el

    create_requests = []
    for plan_slide, slide_id, _ in slide_assignments:
        for icon_spec in plan_slide.get('icons', []):
            icon_name = icon_spec.get('name')
            elem_id = ICON_CATALOG.get(icon_name)
            if not elem_id:
                print(f"  ⚠️  Неизвестная иконка: {icon_name!r}. "
                      f"Доступные: {', '.join(ICON_CATALOG.keys())}")
                continue

            icon_el = icon_elements.get(elem_id)
            if not icon_el:
                print(f"  ⚠️  Иконка {icon_name!r} не найдена в презентации")
                continue

            content_url = icon_el.get('image', {}).get('contentUrl', '')
            if not content_url:
                print(f"  ⚠️  У иконки {icon_name!r} нет contentUrl — пропускаю")
                continue

            # Размер: из плана или из шаблона (реальный с учётом scale)
            el_size = icon_el.get('size', {})
            el_t = icon_el.get('transform', {})
            natural_w = el_size.get('width', {}).get('magnitude', 0) * el_t.get('scaleX', 1)
            natural_h = el_size.get('height', {}).get('magnitude', 0) * el_t.get('scaleY', 1)

            if 'width_cm' in icon_spec:
                w_emu = icon_spec['width_cm'] * CM_TO_EMU
            else:
                w_emu = natural_w if natural_w > 0 else 1.8 * CM_TO_EMU

            if 'height_cm' in icon_spec:
                h_emu = icon_spec['height_cm'] * CM_TO_EMU
            else:
                h_emu = natural_h if natural_h > 0 else 1.8 * CM_TO_EMU

            x_emu = icon_spec.get('x_cm', 0) * CM_TO_EMU
            y_emu = icon_spec.get('y_cm', 0) * CM_TO_EMU

            create_requests.append({
                "createImage": {
                    "url": content_url,
                    "elementProperties": {
                        "pageObjectId": slide_id,
                        "size": {
                            "width":  {"magnitude": w_emu, "unit": "EMU"},
                            "height": {"magnitude": h_emu, "unit": "EMU"}
                        },
                        "transform": {
                            "scaleX": 1, "scaleY": 1,
                            "translateX": x_emu, "translateY": y_emu,
                            "unit": "EMU"
                        }
                    }
                }
            })

    if create_requests:
        print(f"  Размещаю {len(create_requests)} иконок...")
        slides_service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={"requests": create_requests}
        ).execute()


def _get_image_size_px(url: str):
    """Скачивает изображение по URL и возвращает (width_px, height_px) или None."""
    try:
        import urllib.request
        import tempfile
        from PIL import Image as PILImage
        with tempfile.NamedTemporaryFile(suffix='.img', delete=False) as tmp:
            tmp_path = tmp.name
        headers = {'User-Agent': 'Mozilla/5.0'}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            with open(tmp_path, 'wb') as f:
                f.write(resp.read())
        img = PILImage.open(tmp_path)
        return img.size  # (width, height)
    except Exception as e:
        print(f"  ⚠️  Не удалось получить размер картинки: {e}")
        return None


def handle_image_placeholders(slides_service, presentation_id: str,
                               slide_assignments: list):
    """
    Обрабатывает плейсхолдеры картинок на слайдах.

    - Если image_url указан → удаляем IMAGE-плейсхолдер шаблона, вставляем картинку.
    - Если image_url не указан → IMAGE-плейсхолдер остаётся (пользователь вставит вручную).

    Масштабирование: fill без кропа, центрирование в фрейме.
    """
    pres = get_presentation(slides_service, presentation_id)
    slide_elements = {
        slide['objectId']: slide.get('pageElements', [])
        for slide in pres['slides']
    }

    delete_requests = []
    create_requests = []

    for plan_slide, slide_id, elem_map in slide_assignments:
        image_url = plan_slide.get('image_url')
        if not image_url:
            continue

        elements = slide_elements.get(slide_id, [])

        # Ищем самый крупный IMAGE на слайде (плейсхолдер)
        image_frame_elem = None
        best_area = 0
        for elem in elements:
            if 'image' not in elem:
                continue
            s = elem.get('size', {})
            t = elem.get('transform', {})
            eff_w = s.get('width', {}).get('magnitude', 0) * t.get('scaleX', 1)
            eff_h = s.get('height', {}).get('magnitude', 0) * t.get('scaleY', 1)
            area = eff_w * eff_h
            if area > best_area:
                best_area = area
                image_frame_elem = elem

        if image_frame_elem is None:
            print(f"  ⚠️  image_url указан для слайда {slide_id}, "
                  f"но IMAGE-фрейма нет — пропускаю")
            continue

        s = image_frame_elem.get('size', {})
        t = image_frame_elem.get('transform', {})
        frame_w = s.get('width', {}).get('magnitude', 0) * t.get('scaleX', 1)
        frame_h = s.get('height', {}).get('magnitude', 0) * t.get('scaleY', 1)
        frame_x = t.get('translateX', 0)
        frame_y = t.get('translateY', 0)

        delete_requests.append({"deleteObject": {"objectId": image_frame_elem['objectId']}})

        img_size = _get_image_size_px(image_url)
        if img_size:
            img_w_px, img_h_px = img_size
            img_ratio = img_w_px / img_h_px
            frame_ratio = frame_w / frame_h
            if img_ratio < frame_ratio:
                new_h = frame_h
                new_w = frame_h * img_ratio
            else:
                new_w = frame_w
                new_h = frame_w / img_ratio
            cx = frame_x + (frame_w - new_w) / 2
            cy = frame_y + (frame_h - new_h) / 2
        else:
            new_w, new_h = frame_w, frame_h
            cx, cy = frame_x, frame_y

        create_requests.append({
            "createImage": {
                "url": image_url,
                "elementProperties": {
                    "pageObjectId": slide_id,
                    "size": {
                        "width":  {"magnitude": new_w, "unit": "EMU"},
                        "height": {"magnitude": new_h, "unit": "EMU"}
                    },
                    "transform": {
                        "scaleX": 1, "scaleY": 1,
                        "translateX": cx, "translateY": cy,
                        "unit": "EMU"
                    }
                }
            }
        })

    if delete_requests:
        slides_service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={"requests": delete_requests}
        ).execute()
    if create_requests:
        slides_service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={"requests": create_requests}
        ).execute()
        print(f"  Вставлено картинок: {len(create_requests)}")


def apply_transforms(slides_service, presentation_id: str,
                     slide_assignments: list):
    """Применяет трансформации из плана, сохраняя scale из шаблона."""
    pres = get_presentation(slides_service, presentation_id)
    element_lookup = {
        elem['objectId']: elem
        for slide in pres['slides']
        for elem in slide.get('pageElements', [])
    }

    requests = []
    for plan_slide, slide_id, elem_map in slide_assignments:
        for orig_id, t in plan_slide.get("element_transforms", {}).items():
            real_id = elem_map.get(orig_id, orig_id)
            cur = element_lookup.get(real_id, {}).get('transform', {})
            requests.append({
                "updatePageElementTransform": {
                    "objectId": real_id,
                    "applyMode": "ABSOLUTE",
                    "transform": {
                        "scaleX":     t.get("scaleX",  cur.get("scaleX", 1)),
                        "scaleY":     t.get("scaleY",  cur.get("scaleY", 1)),
                        "shearX":     t.get("shearX",  cur.get("shearX", 0)),
                        "shearY":     t.get("shearY",  cur.get("shearY", 0)),
                        "translateX": t["translateX"],
                        "translateY": t["translateY"],
                        "unit": "EMU"
                    }
                }
            })
    if requests:
        slides_service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={"requests": requests}
        ).execute()


def delete_elements(slides_service, presentation_id: str,
                    slide_assignments: list):
    to_delete = []
    for plan_slide, slide_id, elem_map in slide_assignments:
        for orig_id in plan_slide.get("delete_elements", []):
            to_delete.append(elem_map.get(orig_id, orig_id))
    if not to_delete:
        return
    requests = [{"deleteObject": {"objectId": oid}} for oid in to_delete]
    slides_service.presentations().batchUpdate(
        presentationId=presentation_id,
        body={"requests": requests}
    ).execute()


def replace_elements(slides_service, presentation_id: str,
                     slide_assignments: list):
    requests = []
    for plan_slide, slide_id, elem_map in slide_assignments:
        for orig_id, new_text in plan_slide.get("element_replacements", {}).items():
            real_id = elem_map.get(orig_id, orig_id)
            requests.append({
                "deleteText": {"objectId": real_id, "textRange": {"type": "ALL"}}
            })
            if new_text:
                requests.append({
                    "insertText": {
                        "objectId": real_id,
                        "insertionIndex": 0,
                        "text": new_text
                    }
                })
    if requests:
        slides_service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={"requests": requests}
        ).execute()


def apply_target_lines(slides_service, presentation_id: str,
                       slide_assignments: list):
    """
    Изменяет ширину фрейма (scaleX) так, чтобы текст влез в нужное число строк.

    Формат в plan.json:
        "element_target_lines": { "element_id": 2 }
    """
    pres = get_presentation(slides_service, presentation_id)
    element_lookup = {
        elem['objectId']: elem
        for slide in pres['slides']
        for elem in slide.get('pageElements', [])
    }

    requests = []
    for plan_slide, slide_id, elem_map in slide_assignments:
        for orig_id, target in plan_slide.get("element_target_lines", {}).items():
            new_text = plan_slide.get("element_replacements", {}).get(orig_id, "")
            if not new_text or target < 1:
                continue
            real_id = elem_map.get(orig_id, orig_id)
            elem = element_lookup.get(real_id)
            if not elem or 'shape' not in elem:
                continue

            size = elem.get('size', {})
            t = elem.get('transform', {})
            base_w = size.get('width', {}).get('magnitude', 0)
            if base_w <= 0:
                continue

            font_pt = 18.0
            for te in elem['shape'].get('text', {}).get('textElements', []):
                fs = te.get('textRun', {}).get('style', {}).get('fontSize', {})
                if fs.get('magnitude'):
                    font_pt = float(fs['magnitude'])
                    break

            longest = max(len(p) for p in new_text.split('\n'))
            chars_per_line = math.ceil(longest / target)
            needed_w = chars_per_line * font_pt * 12700 * 0.55
            new_scale_x = needed_w / base_w

            requests.append({
                "updatePageElementTransform": {
                    "objectId": real_id,
                    "applyMode": "ABSOLUTE",
                    "transform": {
                        "scaleX":     new_scale_x,
                        "scaleY":     t.get('scaleY', 1),
                        "shearX":     t.get('shearX', 0),
                        "shearY":     t.get('shearY', 0),
                        "translateX": t.get('translateX', 0),
                        "translateY": t.get('translateY', 0),
                        "unit": "EMU"
                    }
                }
            })

    if requests:
        print(f"  Подгоняю ширину {len(requests)} фреймов под целевое число строк...")
        slides_service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={"requests": requests}
        ).execute()


def fit_text_to_frame(slides_service, presentation_id: str,
                      slide_assignments: list):
    """
    Автоматически уменьшает/увеличивает шрифт чтобы текст влезал во фрейм.
    Элементы одного слайда с одинаковым исходным pt выравниваются в одну группу.
    """
    pres = get_presentation(slides_service, presentation_id)

    element_lookup = {}
    for slide in pres['slides']:
        for elem in slide.get('pageElements', []):
            element_lookup[elem['objectId']] = elem

    def estimate_height(text, pt, width_emu):
        char_w = pt * 12700 * 0.55
        cpl = max(1, int(width_emu / char_w))
        lines = sum(
            max(1, math.ceil(max(1, len(p)) / cpl))
            for p in text.split('\n')
        )
        return lines * pt * 12700 * 1.45 + pt * 12700 * 1.0

    def optimal_pt(text, orig_pt, eff_w, eff_h):
        if estimate_height(text, orig_pt, eff_w) <= eff_h:
            best = orig_pt
            for delta in range(1, 6):
                if estimate_height(text, orig_pt + delta, eff_w) <= eff_h:
                    best = orig_pt + delta
                else:
                    break
            return best
        else:
            for delta in range(1, 6):
                c = orig_pt - delta
                if c < 10:
                    return 10
                if estimate_height(text, c, eff_w) <= eff_h:
                    return c
            return max(10, orig_pt - 5)

    groups = defaultdict(list)
    for plan_slide, slide_id, elem_map in slide_assignments:
        overrides = plan_slide.get("font_size_overrides", {})
        target_lines_ids = set(plan_slide.get("element_target_lines", {}).keys())
        for orig_id, new_text in plan_slide.get("element_replacements", {}).items():
            if not new_text or orig_id in overrides or orig_id in target_lines_ids:
                continue
            real_id = elem_map.get(orig_id, orig_id)
            elem = element_lookup.get(real_id)
            if not elem or 'shape' not in elem:
                continue

            size = elem.get('size', {})
            t = elem.get('transform', {})
            eff_w = size.get('width', {}).get('magnitude', 0) * t.get('scaleX', 1)
            eff_h = size.get('height', {}).get('magnitude', 0) * t.get('scaleY', 1)
            if eff_w <= 0 or eff_h <= 0:
                continue

            font_pt = 18.0
            for te in elem['shape'].get('text', {}).get('textElements', []):
                fs = te.get('textRun', {}).get('style', {}).get('fontSize', {})
                if fs.get('magnitude'):
                    font_pt = float(fs['magnitude'])
                    break

            opt = optimal_pt(new_text, font_pt, eff_w, eff_h)
            groups[(slide_id, round(font_pt))].append((real_id, opt))

    requests = []
    for (slide_id, orig_pt), members in groups.items():
        group_min = min(pt for _, pt in members)
        if group_min == orig_pt:
            continue
        for real_id, _ in members:
            requests.append({
                "updateTextStyle": {
                    "objectId": real_id,
                    "textRange": {"type": "ALL"},
                    "style": {
                        "fontSize": {"magnitude": group_min, "unit": "PT"}
                    },
                    "fields": "fontSize"
                }
            })

    if requests:
        print(f"  Выравниваю шрифт в {len(requests)} элементах...")
        slides_service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={"requests": requests}
        ).execute()


def apply_font_sizes(slides_service, presentation_id: str,
                     slide_assignments: list):
    """
    Применяет ручные переопределения размера шрифта из font_size_overrides.

    Формат в plan.json:
        "font_size_overrides": { "element_id": 24 }
    """
    requests = []
    for plan_slide, slide_id, elem_map in slide_assignments:
        for orig_id, size_pt in plan_slide.get("font_size_overrides", {}).items():
            size_pt = max(10, size_pt)
            real_id = elem_map.get(orig_id, orig_id)
            requests.append({
                "updateTextStyle": {
                    "objectId": real_id,
                    "textRange": {"type": "ALL"},
                    "style": {
                        "fontSize": {"magnitude": size_pt, "unit": "PT"}
                    },
                    "fields": "fontSize"
                }
            })
    if requests:
        slides_service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={"requests": requests}
        ).execute()


def build_presentation(plan: dict) -> str:
    creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    slides_service = build('slides', 'v1', credentials=creds, cache_discovery=False)
    drive_service = build('drive', 'v3', credentials=creds, cache_discovery=False)

    title = plan.get("title", "Презентация Trisigma")
    print(f"Копирую шаблон: {title}")
    new_id = copy_template(drive_service, title)
    print(f"Создана копия: https://docs.google.com/presentation/d/{new_id}/edit")

    plan_slides = plan["slides"]
    needs_icons = any(s.get('icons') for s in plan_slides)

    unique_templates = len(set(s["template_id"] for s in plan_slides))
    print(f"Подготавливаю {len(plan_slides)} слайдов ({unique_templates} уникальных шаблонов)...")
    slide_assignments = prepare_slides(slides_service, new_id, plan_slides)

    keep_ids = {sid for _, sid, _ in slide_assignments}
    print("Удаляю лишние слайды...")
    delete_unused_slides(slides_service, new_id, keep_ids, needs_icons)

    print("Переставляю слайды в нужный порядок...")
    ordered_ids = [sid for _, sid, _ in slide_assignments]
    reorder_slides(slides_service, new_id, ordered_ids)

    print("Двигаю и ресайзю элементы...")
    apply_transforms(slides_service, new_id, slide_assignments)

    print("Удаляю ненужные элементы...")
    delete_elements(slides_service, new_id, slide_assignments)

    print("Обрабатываю плейсхолдеры картинок...")
    handle_image_placeholders(slides_service, new_id, slide_assignments)

    if needs_icons:
        print("Размещаю иконки...")
        place_icons(slides_service, new_id, slide_assignments)
        print("Удаляю слайды с иконками...")
        delete_icon_slides(slides_service, new_id)

    # apply_target_lines ДОЛЖЕН идти ДО replace_elements
    print("Подгоняю ширину фреймов под целевое число строк...")
    apply_target_lines(slides_service, new_id, slide_assignments)

    print("Заменяю текст...")
    replace_elements(slides_service, new_id, slide_assignments)

    print("Подгоняю шрифт под размер фреймов...")
    fit_text_to_frame(slides_service, new_id, slide_assignments)

    print("Применяю переопределения размера шрифта...")
    apply_font_sizes(slides_service, new_id, slide_assignments)

    return new_id


def main():
    if len(sys.argv) < 2:
        print("Использование: python3 create_presentation.py plan.json")
        sys.exit(1)

    with open(sys.argv[1], 'r', encoding='utf-8') as f:
        plan = json.load(f)

    print(f"Загружен план: {plan['title']}")
    print(f"Слайдов: {len(plan['slides'])}")
    for i, slide in enumerate(plan['slides'], 1):
        print(f"  {i}. {slide['description']}")

    if "expected_slide_count" in plan:
        expected = plan["expected_slide_count"]
        actual = len(plan["slides"])
        if actual != expected:
            print(f"\n❌ Ошибка: expected_slide_count={expected}, "
                  f"но слайдов в slides[] — {actual}.")
            print("Исправь plan.json перед запуском.")
            sys.exit(1)
        print(f"✓ Количество слайдов совпадает с ожидаемым: {expected}")

    print("\nСобираю презентацию...")
    new_id = build_presentation(plan)

    print(f"\nГотово!")
    print(f"Открыть: https://docs.google.com/presentation/d/{new_id}/edit")


if __name__ == "__main__":
    main()

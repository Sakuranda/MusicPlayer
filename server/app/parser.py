"""标题 → 歌曲名/歌手 解析（针对虚拟主播翻唱切片优化）。

B 站翻唱标题常见形态：
- 【翻唱】夜に駆ける / YOASOBI【沙花叉クロヱ】
- 【歌ってみた】ド屑 歌ってみた【星街すいせい】
- GOD KNOWS... 歌ってみた - 潤羽るしあ
- 【東雪蓮】打上花火
- cover《los! los! los!》by xxx

策略：
1. 先剥离 "by xxx"（by 后是歌手）；
2. 提取所有【】（）《》「」内容；只把「像人名」的内容当歌手（纯中日文短名、
   含"唱"等提示词、或与标签/UP主一致）；
3. 歌曲名 = 主标题去掉括号、噪音词后；按分隔符切分时优先中日文部分；
4. 解析是启发式，前端提供预览让用户确认/修改。
"""
import re

# 纯噪音标签（既不是歌名也不是歌手）
NOISE_TAGS = {
    "翻唱", "翻唱版", "歌ってみた", "試唱", "试唱", "歌枠", "歌回",
    "cover", "Cover", "COVER", "カバー", "音乐", "音楽", "music", "MV", "MMD",
    "切り抜き", "切片", "录播", "直播", "完整版", "高音質", "高音质", "无损",
    "原創", "原创", "初投稿", "投稿", "新作", "4k", "1080p", "60fps", "音源",
    "作业用", "作業用", "作業用bgm", "bgm", "BGM", "无修音", "修音",
    "生唱", "耳コピ", "自弹自唱", "弹唱", "生放送", "配信", "唱见",
    "vup", "VUP", "vtb", "vtuber", "VTuber", "虚拟主播", "歌势",
    "3d", "3D", "2d", "2D", "live", "LIVE", "official", "Official",
    "耐久", "自我介绍", "自我介紹", "雑談", "杂谈",
}

# 提示“后面是人名”的词
SINGER_HINTS = ("唱", "翻唱", "演唱", "歌手", "歌い手", "歌勢")

# 可能混在标题里的原唱歌手提示词
ORIGINAL_HINTS = ("原唱", "本家", "オリジナル", "original")

BRACKET_RE = re.compile(r"[【\[〔][^】\]〕]{1,40}[】\]〕]|[（(][^）)]{1,40}[）)]|[《「『][^》」』]{1,40}[》」』]")

_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
_LATIN_RE = re.compile(r"[a-zA-Z]")


def _clean_noise(text: str) -> str:
    """去掉标题中的噪音词。"""
    t = text
    # 长的先替换，防止“投稿”先于“初投稿”被删掉
    for w in sorted(NOISE_TAGS, key=len, reverse=True):
        if _LATIN_RE.search(w):
            t = re.sub(rf"(?i)\b{re.escape(w)}\b", " ", t)
        else:
            t = t.replace(w, " ")
    # 残留的孤立"生"（"生歌枠"去掉歌枠后）
    t = re.sub(r"(^|\s)生(?=\s|$)", " ", t)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip(" -–—/、·~")


def _name_like(s: str) -> bool:
    """判断更像人名（中日文短名，不含拉丁字母与符号）。"""
    if not s:
        return False
    s = s.strip()
    if _LATIN_RE.search(s) or re.search(r"[0-9!?&+/·.,，。！？]", s):
        return False
    return 2 <= len(s) <= 12


def _looks_like_song(s: str) -> bool:
    if not s:
        return False
    s = s.strip()
    if len(s) <= 1:
        return False
    if any(h in s for h in SINGER_HINTS) or any(h in s for h in ORIGINAL_HINTS):
        return False
    return bool(re.search(r"[a-zA-Z0-9.!?~&+\-–—/、\s]", s)) or len(s) >= 5


def parse_title(raw_title: str, uploader: str = "", tags: list[str] | None = None) -> tuple[str, str]:
    """返回 (歌曲名, 歌手)。"""
    tags = tags or []
    title = (raw_title or "").strip()

    # 1. by xxx → 歌手
    artist = ""
    m = re.search(r"(?:^|\W)[bB][yY]\s+(.+)$", title)
    if m:
        artist = _clean_noise(m.group(1))
        end = m.start()
        # \W 匹配到的是右括号时保留它（如 《los! los! los!》by xxx）
        if end < len(title) and title[end] in "》」』)】]〕":
            end += 1
        title = title[:end].strip()

    # 2. 括号内容
    brackets = BRACKET_RE.findall(title)
    body = BRACKET_RE.sub(" ", title)

    singer_candidates = []
    for b in brackets:
        inner = _clean_noise(b[1:-1])
        if not inner:
            continue
        if any(h in inner for h in SINGER_HINTS):
            inner = _clean_noise(re.split(r"[翻唱演唱/]", inner)[0])
        if not inner or any(h in inner for h in ORIGINAL_HINTS):
            continue
        # 人名特征或与标签/UP主一致
        if _name_like(inner) or inner in tags or inner == uploader:
            singer_candidates.append(inner)

    if not artist and singer_candidates:
        artist = singer_candidates[-1]  # 结尾括号优先

    # 标签里找歌手
    if not artist:
        for t in tags:
            if any(h in t for h in SINGER_HINTS):
                t2 = _clean_noise(re.split(r"[翻唱演唱]", t)[0])
                if t2 and t2 != uploader:
                    artist = t2
                    break
    if not artist:
        artist = uploader or ""

    # 3. 歌曲名
    body = _clean_noise(body)
    song = body
    for sep in (" - ", " – ", " — ", "/"):
        if sep in body:
            parts = [p for p in (_clean_noise(x) for x in body.split(sep)) if p]
            if len(parts) >= 2:
                # 某一部分是 UP 主本人 → 它是歌手，歌曲取其余部分
                up_part = None
                if uploader:
                    for p in parts:
                        if p == uploader or (len(uploader) >= 3 and p in uploader):
                            up_part = p
                            break
                if up_part:
                    if not artist:
                        artist = uploader
                    others = [p for p in parts if p != up_part]
                    cjk = [p for p in others if _CJK_RE.search(p)]
                    song = max(cjk or others, key=len)
                    break
                # 优先中日文部分（如 "夜に駆ける / YOASOBI"）；
                # 多个中日文部分时取第一个（如 "ふわふわ時間 / 放課後ティータイム"）
                cjk = [p for p in parts if _CJK_RE.search(p)]
                if len(cjk) == 1:
                    song = cjk[0]
                elif cjk:
                    song = parts[0] if _CJK_RE.search(parts[0]) else max(cjk, key=len)
                else:
                    song = max(parts, key=len)
                if not artist:
                    others = [p for p in parts if p != song]
                    names = [p for p in others if _name_like(p)]
                    if names:
                        artist = names[-1]
                break

    # 主标题为空 → 从括号里找像歌名的内容
    if not song:
        for b in brackets:
            inner = _clean_noise(b[1:-1])
            if inner and not _name_like(inner) and _looks_like_song(inner):
                song = inner
                break
    if not song:
        song = _clean_noise(title)

    # 去掉歌名里残留的歌手名
    if artist and artist in song and song != artist:
        song = song.replace(artist, " ").strip(" -–—/、·~")
        song = re.sub(r"\s{2,}", " ", song).strip()

    return song or title, artist.strip()

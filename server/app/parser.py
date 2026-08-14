"""标题 → 歌曲名/歌手 解析（针对虚拟主播翻唱切片优化）。

B 站翻唱视频常见形态：
A. 书名号里是歌名：《说好的幸福呢》|“只是回忆的音乐盒还旋转着…”
B. 标题=歌词金句，歌名在标签里：“永远爱你是我说过…” tags:[我们俩, 郭顶]
C. 标题含歌名：【翻唱】夜に駆ける / YOASOBI【沙花叉クロヱ】
D. 切片（歌切）：UP主是剪辑号，歌手在【】或标签里（小雾uya）

策略（按信号强弱）：
1. 《》「」『』内容 → 歌名（最强信号）
2. by xxx → 歌手；【】〔〕内容 → 歌手候选（呜米x咩栗 → 呜米）
3. 标题切分（- — / 丨 |）→ 歌名候选（含“歌手 - 歌名”逆序识别）
4. 标题像“句子/歌词”或纯人名 → 从标签挖歌名（排除噪音词/原唱歌手名单）
5. 歌手 = 【】人名 > 标题残留人名 > 标签主播名（聚类去重）> UP主
解析是启发式，前端提供预览让用户确认/修改。
"""
import re

# 纯噪音标签/词（既不是歌名也不是人名）
NOISE_TAGS = {
    "翻唱", "翻唱版", "歌ってみた", "試唱", "试唱", "歌枠", "歌回",
    "cover", "Cover", "COVER", "カバー", "音乐", "音楽", "music", "MV", "MMD",
    "切り抜き", "切片", "录播", "直播", "直播回放", "完整版", "高音質", "高音质", "无损",
    "原創", "原创", "初投稿", "投稿", "新作", "4k", "1080p", "60fps", "音源",
    "作业用", "作業用", "作業用bgm", "bgm", "BGM", "无修音", "修音", "精修",
    "生唱", "耳コピ", "自弹自唱", "弹唱", "尤克里里弹唱", "生放送", "配信", "唱见",
    "vup", "VUP", "vtb", "vtuber", "VTuber", "VTUBER", "虚拟主播", "歌势",
    "3d", "3D", "2d", "2D", "live", "LIVE", "official", "Official",
    "耐久", "自我介绍", "自我介紹", "雑談", "杂谈",
    "女声", "男声", "女声翻唱", "中文翻唱", "日文翻唱", "日语翻唱",
    "双女", "双女声", "女声合唱", "合唱",
    "治愈", "温柔", "青春", "可爱", "萌宠", "美女", "暗恋", "苦情", "苦情歌",
    "情歌", "纯爱", "甜歌", "氛围", "暧昧", "空心", "emo", "be", "BE", "唱歌",
    "听歌", "音乐分享官", "翻唱总动员", "竖屏音乐会", "虚拟最强音",
    "全能音乐挑战赛", "2022虚拟歌手创作赛", "原创手书", "挚友", "回忆", "烟花",
    "恋爱", "oc", "OC", "记录", "歌切", "二次元", "演奏", "重制", "爵士", "爵士乐",
    "翻唱的N种打开方式", "虚拟偶像", "虚拟UP主", "虚拟up主", "虚拟歌手", "虚拟YOUTUBER",
    "打卡挑战", "百日挑战", "MeUmy百日翻唱挑战", "星穹列车启航庆典", "我的演奏高光时刻",
    "和平精英古墓迷途", "和平精英共闯火山", "碧蓝幻想Relink无尽", "彩六干员请就位",
    "光遇致梵高", "炉石传说逃离紫罗兰监狱", "炉石传说", "一梦江湖新门派落白",
    "VRC", "vrc", "宝宝巴士", "EVA3.0+1", "新世纪福音战士", "eva",
    "日文", "中文", "日语", "日語", "国语", "英语", "英文", "hires", "HiRes",
}

# 原唱歌手/创作者（常出现在标签里，但不是本曲歌手，也不作为歌名）
ORIGINAL_ARTISTS = {
    "aimer", "陈奕迅", "郭顶", "周杰伦", "蔡健雅", "米津玄師", "米津玄师",
    "徐佳莹", "许嵩", "告五人", "任然", "葛东琪", "江语晨", "邹佩佩",
    "deca joins", "西沢さんp", "宇多田光", "宇多田ヒカル",
    "万能和弦", "新裤子", "房东的猫", "汪苏泷", "薛之谦", "林俊杰", "王菲",
    "邓紫棋", "张杰", "李荣浩", "毛不易", "陈粒",
    "yoasobi", "夜鹿", "ヨルシカ", "ずっと真夜中でいいのに", "真夜中",
    "ado", "eve", "vaundy", "藤井风", "藤井風", "優里", "yama", "milet",
    "ikura", "幾田りら", "あいみょん", "mizuki", "zutomayo", "radwimps",
    "one ok rock", "king gnu", "official髭男dism", "打首獄門同好会",
    "放課後ティータイム", "泽野弘之", "梶浦由记", "vocaloid", "初音ミク",
    "初音未来", "镜音", "gumi", "flower", "可不", "重音テト", "重音teto",
}

# 提示“后面是人名”的词
SINGER_HINTS = ("唱", "翻唱", "演唱", "歌手", "歌い手", "歌勢")

# 可能混在标题里的原唱歌手提示词
ORIGINAL_HINTS = ("原唱", "本家", "オリジナル", "original")

# 【】〔〕→ 歌手候选；《》「」『』→ 歌名候选；（）→ 其他
PERSON_BRACKET_RE = re.compile(r"[【\[〔]([^】\]〕]{1,40})[】\]〕]")
BOOK_RE = re.compile(r"[《「『]([^》」』]{1,40})[》」』]")
PAREN_RE = re.compile(r"[（(]([^）)]{1,40})[）)]")

_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
_LATIN_RE = re.compile(r"[a-zA-Z]")

# 判断标题像“句子/歌词”的特征
_SENTENCE_PARTICLES = (
    "的", "了", "我", "你", "他", "她", "是", "在", "有", "就", "都", "不", "会",
    "能", "吗", "吧", "呢", "着", "过", "一起", "什么", "时候", "感觉", "终于",
    "还是", "总是", "再被", "我们", "永远", "真的", "如果", "因为", "是不是",
)
_QUOTE_RE = re.compile(r"[“”\"'|丨]|…|\.\.\.")

# 连唱挑战等运营活动标题（书名号里出现时不是歌名）
_CAMPAIGN_RE = re.compile(r"day\s*\d+|\d+\s*天|连唱|连唱\d|挑战|合集", re.I)


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
    return t.strip(" -–—/、·~|丨！!？?")


def _person_like(s: str) -> bool:
    """判断像人名/主播名：含中日文、长度 2-16、无数字。
    允许拉丁字母（小雾uya / 雾氧Uo），但排除纯英文。"""
    if not s:
        return False
    s = s.strip()
    if not _CJK_RE.search(s):
        return False
    if re.search(r"[0-9!?&+/·.,，。！？x×]", s):
        return False
    return 2 <= len(s) <= 16


def _name_like(s: str) -> bool:
    """严格人名：纯中日文（无拉丁），长度 ≤ 6。"""
    if not _person_like(s):
        return False
    return not _LATIN_RE.search(s) and len(s) <= 6


def _looks_like_song(s: str) -> bool:
    if not s:
        return False
    s = s.strip()
    if len(s) <= 1:
        return False
    if any(h in s for h in SINGER_HINTS) or any(h in s for h in ORIGINAL_HINTS):
        return False
    return bool(re.search(r"[a-zA-Z0-9.!?~&+\-–—/、\s]", s)) or len(s) >= 5


def _sentence_like(s: str) -> bool:
    """标题像句子/歌词摘录（而不是歌名）。纯英文/纯外文标题不算。"""
    if not s:
        return False
    s = s.strip()
    # 纯拉丁字母标题（One Last Kiss）不是句子
    if _LATIN_RE.search(s) and not _CJK_RE.search(s):
        return False
    if _QUOTE_RE.search(s):
        return True
    if len(s) > 12:
        return True
    return any(p in s for p in _SENTENCE_PARTICLES)


def _is_noise_word(w: str) -> bool:
    low = w.lower()
    return low in {x.lower() for x in NOISE_TAGS} or low in {x.lower() for x in ORIGINAL_ARTISTS}


def _tag_song_candidates(tags: list[str]) -> list[str]:
    """从标签里挑歌名候选。"""
    out = []
    for t in tags:
        t = t.strip()
        if not t or len(t) > 24 or _is_noise_word(t):
            continue
        if _CAMPAIGN_RE.search(t):
            continue
        if any(h in t for h in SINGER_HINTS) or any(h in t for h in ORIGINAL_HINTS):
            continue
        out.append(t)
    return out


def _best_song_from_tags(candidates: list[str], title: str) -> str:
    if not candidates:
        return ""
    cjk = [c for c in candidates if _CJK_RE.search(c) and not _LATIN_RE.search(c)]
    pool = cjk or candidates
    for c in pool:
        if c and c in title:
            return c
    return max(pool, key=len)


def _artist_from_tags(tags: list[str], uploader: str, song: str) -> str:
    """从标签里识别主播/歌手名（聚类处理“阿梓/阿梓从小就很可爱”）。"""
    names = []
    for t in tags:
        t = t.strip()
        if not _person_like(t) or _is_noise_word(t):
            continue
        if t == song or t in song or song in t:
            continue
        if t == uploader:
            continue
        names.append(t)
    if not names:
        return ""
    clusters: list[str] = []
    for n in sorted(names, key=len):
        hit = False
        for i, c in enumerate(clusters):
            if n in c or c in n:
                clusters[i] = max(c, n, key=len)
                hit = True
                break
        if not hit:
            clusters.append(n)
    if len(clusters) == 1:
        return clusters[0]
    return ""


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
        if end < len(title) and title[end] in "》」』)】]〕":
            end += 1
        title = title[:end].strip()

    # 2. 书名号内容 → 歌名候选（最强信号）
    book_cands = []
    for inner in BOOK_RE.findall(title):
        c = _clean_noise(inner)
        if not c:
            continue
        c = re.sub(r"[x×]$", "", c).strip()  # “悬溺x空心”→ 悬溺x → 悬溺
        if c and not _CAMPAIGN_RE.search(c) and not _is_noise_word(c):
            book_cands.append(c)

    # 3. 【】人名候选（“呜米x咩栗”取前者；“阿梓歌”→“阿梓”）
    person_cands = []
    for inner in PERSON_BRACKET_RE.findall(title):
        c = _clean_noise(inner)
        if not c or _CAMPAIGN_RE.search(c):
            continue
        if "x" in c or "×" in c:
            c = re.split(r"[x×]", c)[0].strip()
        c = re.sub(r"(?i)diffsinger$", "", c).strip()
        if len(c) > 2 and c.endswith("歌") and _name_like(c[:-1]):
            c = c[:-1]
        if c and not _is_noise_word(c) and _person_like(c):
            person_cands.append(c)

    # 4. 去掉括号后的主体
    body = PERSON_BRACKET_RE.sub(" ", title)
    body = BOOK_RE.sub(" ", body)
    body = PAREN_RE.sub(" ", body)
    body = _clean_noise(body)

    # 5. 标题切分 → 歌名候选
    title_song = body
    for sep in (" - ", " – ", " — ", " / ", "/", "丨", "|", "-", "—"):
        if sep in body:
            parts = [p for p in (_clean_noise(x) for x in body.split(sep)) if p]
            if len(parts) < 2:
                continue
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
                title_song = max(cjk or others, key=len)
                break
            cjk = [p for p in parts if _CJK_RE.search(p)]
            latin = [p for p in parts if not _CJK_RE.search(p)]
            # “歌手 - 歌名”逆序：英文部分不是原唱歌手 → 英文是歌名（早稻叽 - One Last Kiss）
            if cjk and latin and all(_person_like(p) for p in cjk):
                known = [p for p in latin if p.lower() in {a.lower() for a in ORIGINAL_ARTISTS}]
                if not known:
                    title_song = max(latin, key=len)
                    if not artist:
                        names = [p for p in cjk if _name_like(p)]
                        if names:
                            artist = names[-1]
                    break
            # “歌名 / 原唱歌手”：英文部分是原唱歌手 → 中日文是歌名
            if len(cjk) == 1:
                title_song = cjk[0]
            elif cjk:
                title_song = parts[0] if _CJK_RE.search(parts[0]) else max(cjk, key=len)
            else:
                title_song = max(parts, key=len)
            if not artist:
                others = [p for p in parts if p != title_song]
                names = [p for p in others if _name_like(p) and not _sentence_like(p)]
                if names:
                    artist = names[-1]
            break

    # 6. 歌名决策（信号优先级：书名号 > 标题 > 标签 > 英文短语）
    tag_cands = _tag_song_candidates(tags)
    song = ""
    if book_cands:
        song = max(book_cands, key=len)
    elif title_song and not _sentence_like(title_song):
        # 标题本身像歌名：直接采用。
        # 例外：标题是纯人名且无【】人名 → 歌名在标签里（早稻叽 / 雾氧Uo 等）
        if (
            _name_like(title_song)
            and not person_cands
            and tag_cands
            and title_song != uploader
        ):
            song = _best_song_from_tags(tag_cands, title)
            if song and not artist and title_song != song:
                artist = title_song
        else:
            song = title_song
    elif _sentence_like(title_song) and tag_cands:
        song = _best_song_from_tags(tag_cands, title)
        # 若标签选出的“歌名”其实是【】里的人名（阿梓），优先取标题里的英文歌名
        if song and _person_like(song) and any(song == p or p in song or song in p for p in person_cands):
            phrases = re.findall(r"[A-Za-z]+(?:\s+[A-Za-z]+)+", body)
            if phrases:
                song = max(phrases, key=len)
    if not song:
        song = _best_song_from_tags(tag_cands, title)
    if not song:
        # 句子标题里的英文歌名（“学会One Last Kiss给梓宝上总督”）
        phrases = re.findall(r"[A-Za-z]+(?:\s+[A-Za-z]+)+", body)
        if phrases:
            song = max(phrases, key=len)
    if not song:
        song = title_song or title

    # 7. 歌手决策
    if not artist:
        # 【】人名（排除与歌名相同的，如【下雨天】）
        for c in reversed(person_cands):
            if c != song and c not in song and song not in c:
                artist = c
                break
    if not artist:
        # 标题残留若是短人名 → 歌手（雾氧Uo《说好的幸福呢》）
        # 仅在标题未被切分过时使用（恋人-小雾uya 已由切分处理）
        body_name = _clean_noise(body)
        if (
            title_song == body
            and song
            and body_name
            and body_name != song
            and not _sentence_like(body_name)
            and _person_like(body_name)
            and (_LATIN_RE.search(body_name) or len(body_name) <= 5)
            and not _is_noise_word(body_name)
        ):
            artist = body_name
    if not artist:
        artist = _artist_from_tags(tags, uploader, song)
    if not artist:
        for t in tags:
            if _is_noise_word(t) or t == song:
                continue
            if any(h in t for h in SINGER_HINTS):
                t2 = _clean_noise(re.split(r"[翻唱演唱]", t)[0])
                if t2 and _person_like(t2) and t2 != uploader and t2 != song:
                    artist = t2
                    break
    if not artist:
        artist = uploader or ""

    # 8. 收尾清理
    if artist and artist in song and song != artist:
        song = song.replace(artist, " ").strip(" -–—/、·~|丨")
        song = re.sub(r"\s{2,}", " ", song).strip()

    return song or title, artist.strip()

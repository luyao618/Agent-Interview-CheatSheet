#!/usr/bin/env python3
"""Build self-contained question pages from Markdown, with no runtime dependencies."""
from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass, field
from hashlib import sha256
from html import escape
from html.parser import HTMLParser
import json
import mimetypes
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import yaml
from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / 'templates' / 'question'
PARSER = MarkdownIt('gfm-like', {'html': True})
DIFFICULTIES = {'easy': '入门', 'medium': '进阶', 'hard': '困难'}
ROLES = {'engineer': '工程师', 'pm': '产品经理', 'both': '工程师 / 产品经理'}
FOLLOWUP_SECTIONS = {'延伸 / 追问', '追问'}
FOLLOWUP_PREFIX = re.compile(r'^追问\s*(?:[\d一二三四五六七八九十]+\s*)?[：:]\s*')
GENERATED_MARKER = '<meta name="generator" content="scripts/gen_html.py">'


@dataclass
class Followup:
    title: str
    answer: str


@dataclass
class Answer:
    heading: str
    body: str
    metadata: dict


@dataclass
class Question:
    path: Path
    entry: dict
    metadata: dict
    prompt: str
    answers: list[Answer] = field(default_factory=list)
    followups: list[Followup] = field(default_factory=list)
    extras: list[tuple[str, str]] = field(default_factory=list)
    source_hash: str = ''

    @property
    def output_name(self):
        return self.path.with_suffix('.html').name


class TextOnly(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain(markdown_text):
    parser = TextOnly()
    parser.feed(PARSER.renderInline(markdown_text))
    return ''.join(parser.parts)


def header_parts(raw):
    """Recognize an actual question header, never a bold answer statement."""
    raw = re.sub(r'^\s*(?:[-+*]|\d+[.)])\s+', '', raw.strip())
    match = re.match(r'^\*\*(.+?)\*\*(.*)$', raw)
    if match:
        title, tail = match.groups()
        if FOLLOWUP_PREFIX.match(title) or re.search(r'[?？]', plain(title)):
            return FOLLOWUP_PREFIX.sub('', title).strip(), tail.strip()
    elif re.search(r'[?？]\s*$', raw):
        return FOLLOWUP_PREFIX.sub('', raw), ''
    return None


def question_starts(markdown_text, explicit_only=False):
    lines = markdown_text.splitlines(keepends=True)
    tokens = PARSER.parse(markdown_text)
    starts = []
    for token in tokens:
        if not token.map:
            continue
        if not ((token.type == 'paragraph_open' and token.level == 0) or
                (token.type == 'list_item_open' and token.level == 1)):
            continue
        first = lines[token.map[0]].strip()
        stripped = re.sub(r'^(?:[-+*]|\d+[.)])\s+', '', first)
        if explicit_only and not re.match(r'^\*\*追问\s*(?:[\d一二三四五六七八九十]+\s*)?[：:]', stripped):
            continue
        parts = header_parts(first)
        if parts:
            starts.append((token.map[0], token.map[1], parts, token.type == 'list_item_open'))
    return starts


def peel_followup(raw, is_list):
    lines = raw.splitlines()
    if is_list:
        marker = re.match(r'^(\s*(?:[-+*]|\d+[.)])\s+)', lines[0])
        if marker:
            width = len(marker[1])
            lines[0] = lines[0][width:]
            lines[1:] = [line[width:] if line.startswith(' ' * width) else line for line in lines[1:]]
    title, tail = header_parts(lines[0])
    return Followup(title, '\n'.join([tail, *lines[1:]]).strip())


def split_followups(body):
    """Split dedicated follow-up sections; return any introductory prose intact."""
    lines = body.splitlines(keepends=True)
    starts = question_starts(body)
    if not starts and body.strip():
        raise ValueError('Unrecognized follow-up format; refusing to silently omit content')
    followups = []
    for i, (start, _, _, is_list) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(lines)
        followups.append(peel_followup(''.join(lines[start:end]), is_list))
    intro = ''.join(lines[:starts[0][0]]).strip() if starts else ''
    return followups, intro


def extract_embedded_followups(body):
    """Lift explicit inline follow-up items out of mixed misconceptions sections."""
    lines = body.splitlines(keepends=True)
    starts = question_starts(body, explicit_only=True)
    followups = []
    consumed = set()
    for start, end, _, is_list in starts:
        followups.append(peel_followup(''.join(lines[start:end]), is_list))
        consumed.update(range(start, end))
    remaining = ''.join(line for i, line in enumerate(lines) if i not in consumed)
    return remaining.strip(), followups


def parse_question(path, entry):
    raw = path.read_text(encoding='utf-8')
    match = re.match(r'\A---\s*\n([\s\S]*?)\n---\s*\n', raw)
    if not match:
        raise ValueError(f'{path.name}: missing YAML frontmatter')
    metadata = yaml.safe_load(match[1])
    if metadata['id'] != entry['id'] or metadata['title'] != entry['title']:
        raise ValueError(f'{path.name}: index/frontmatter identity mismatch')
    body = raw[match.end():]
    lines = body.splitlines(keepends=True)
    tokens = PARSER.parse(body)
    headings = [(token.map[0], token.map[1], tokens[i + 1].content)
                for i, token in enumerate(tokens)
                if token.type == 'heading_open' and token.tag == 'h2' and token.level == 0]
    if not headings or ''.join(lines[:headings[0][0]]).strip():
        raise ValueError(f'{path.name}: unexpected content before question section')
    question = Question(path, entry, metadata, '', source_hash=sha256(raw.encode()).hexdigest())
    for i, (_, start, heading) in enumerate(headings):
        end = headings[i + 1][0] if i + 1 < len(headings) else len(lines)
        content = ''.join(lines[start:end]).strip()
        if heading == '问题':
            question.prompt = content
        elif heading.startswith('答案'):
            content, embedded = extract_embedded_followups(content)
            question.followups.extend(embedded)
            author = heading.split('·', 1)[1].strip() if '·' in heading else None
            candidates = metadata.get('answers', [])
            answer_meta = next((a for a in candidates if a.get('author') == author), None)
            if answer_meta is None:
                answer_meta = candidates[len(question.answers)] if len(question.answers) < len(candidates) else {}
            # The attribution is rendered once in the answer header, not duplicated.
            content = re.sub(r'^>\s*🤖 AI 答案[^\n]*(?:\n\s*)?', '', content, count=1)
            question.answers.append(Answer(heading, content, answer_meta))
        elif heading in FOLLOWUP_SECTIONS:
            followups, intro = split_followups(content)
            question.followups.extend(followups)
            if intro:
                question.extras.append(('延伸说明', intro))
        else:
            content, embedded = extract_embedded_followups(content)
            question.followups.extend(embedded)
            question.extras.append((heading, content))
    if not question.prompt or not question.answers or any(not a.body for a in question.answers):
        raise ValueError(f'{path.name}: missing prompt or answer')
    if len(question.answers) != entry['answers_count']:
        raise ValueError(f'{path.name}: answer count differs from index')
    return question


class SafeRawHTML(HTMLParser):
    """Only retain inert formatting used by the source; code fences bypass this."""
    allowed = {'details', 'summary', 'br', 'sub', 'sup', 'kbd'}

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        self.parts.append(f'<{tag}>' if tag in self.allowed else escape(self.get_starttag_text()))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        self.parts.append(f'</{tag}>' if tag in self.allowed else escape(f'</{tag}>'))

    def handle_data(self, data):
        self.parts.append(escape(data, quote=False))

    def handle_entityref(self, name):
        self.parts.append(f'&{name};')

    def handle_charref(self, name):
        self.parts.append(f'&#{name};')

    def handle_comment(self, data):
        pass


def safe_raw(text):
    parser = SafeRawHTML()
    parser.feed(text)
    return ''.join(parser.parts)


class DiagramRenderer:
    def __init__(self, check=False):
        self.cache = TEMPLATES / 'diagrams'
        self.cache.mkdir(exist_ok=True)
        self.check = check
        self.used = set()

    def render(self, source):
        key = sha256(source.encode()).hexdigest()
        self.used.add(key)
        cache_file = self.cache / f'{key}.svg'
        if not cache_file.exists():
            executable = ROOT / 'scripts/diagram-renderer/node_modules/.bin/mmdc'
            if self.check or not executable.exists():
                raise ValueError('Missing static diagram cache. Run npm --prefix scripts/diagram-renderer ci, then regenerate HTML.')
            with tempfile.TemporaryDirectory(prefix='interview-diagram-') as tmp:
                tmp = Path(tmp)
                (tmp / 'diagram.mmd').write_text(source)
                config = {'deterministicIds': True, 'deterministicIDSeed': key,
                          'securityLevel': 'strict', 'theme': 'base',
                          'themeVariables': {'primaryColor': '#e9eeff', 'primaryTextColor': '#202d48',
                                            'primaryBorderColor': '#9aaee9', 'lineColor': '#697ea8',
                                            'fontFamily': 'Arial, PingFang SC, sans-serif'},
                          'flowchart': {'htmlLabels': False}, 'htmlLabels': False}
                (tmp / 'config.json').write_text(json.dumps(config))
                command = [str(executable), '-i', str(tmp / 'diagram.mmd'), '-o', str(tmp / 'diagram.svg'),
                           '-c', str(tmp / 'config.json'), '-b', 'transparent', '-w', '1200', '-q']
                browser = os.environ.get('PUPPETEER_EXECUTABLE_PATH')
                if browser:
                    (tmp / 'browser.json').write_text(json.dumps({'executablePath': browser}))
                    command += ['-p', str(tmp / 'browser.json')]
                subprocess.run(command, check=True, timeout=90, cwd=ROOT)
                svg = (tmp / 'diagram.svg').read_bytes()
                if b'<svg' not in svg or b'<script' in svg:
                    raise ValueError('Diagram renderer returned an invalid SVG')
                cache_file.write_bytes(svg)
        svg = cache_file.read_text()
        # Explicit intrinsic dimensions make full-size viewing work for SVG data URLs.
        viewbox = re.search(r'viewBox="([^"]+)"', svg)
        width, height = [float(value) for value in viewbox[1].split()][2:]
        root = re.search(r'<svg\b[^>]*>', svg)[0]
        normalized = re.sub(r'\s(?:width|height)="[^"]*"', '', root)
        normalized = normalized[:-1] + f' width="{width:g}" height="{height:g}">'
        svg = svg.replace(root, normalized, 1)
        uri = 'data:image/svg+xml;base64,' + base64.b64encode(svg.encode()).decode()
        return uri, key, width, height


def data_uri(path):
    mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
    return f'data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}'


class ContentRenderer:
    def __init__(self, question, file_map, output_dir, diagrams):
        self.question = question
        self.file_map = file_map
        self.output_dir = output_dir
        self.diagrams = diagrams
        self.heading_ids = set()
        self.code_blocks = 0
        self.images = 0
        self.md = MarkdownIt('gfm-like', {'html': True})
        self.md.add_render_rule('html_block', lambda renderer, tokens, idx, options, env: safe_raw(tokens[idx].content))
        self.md.add_render_rule('html_inline', lambda renderer, tokens, idx, options, env: safe_raw(tokens[idx].content))
        self.md.add_render_rule('fence', lambda renderer, tokens, idx, options, env: self.fence(renderer, tokens, idx, options, env))
        self.md.add_render_rule('code_block', lambda renderer, tokens, idx, options, env: self.fence(renderer, tokens, idx, options, env))
        self.md.add_render_rule('link_open', lambda renderer, tokens, idx, options, env: self.link_open(renderer, tokens, idx, options, env))
        self.md.add_render_rule('image', lambda renderer, tokens, idx, options, env: self.image(renderer, tokens, idx, options, env))
        self.md.add_render_rule('heading_open', lambda renderer, tokens, idx, options, env: self.heading_open(renderer, tokens, idx, options, env))
        self.md.add_render_rule('table_open', lambda renderer, tokens, idx, options, env: '<div class="table-wrap" role="region" aria-label="表格" tabindex="0"><table>\n')
        self.md.add_render_rule('table_close', lambda renderer, tokens, idx, options, env: '</table></div>\n')

    def resolve_url(self, url, image=False):
        parts = urlsplit(url)
        if parts.scheme or parts.netloc or not parts.path:
            return url
        target = (self.question.path.parent / unquote(parts.path)).resolve()
        if not target.is_relative_to(ROOT):
            raise ValueError(f'{self.question.path.name}: local URL leaves repository: {url}')
        if not target.exists():
            raise ValueError(f'{self.question.path.name}: missing local asset/link: {url}')
        if target in self.file_map:
            fragment = {'问题': 'question-title', '答案': 'reference-answer', '追问': 'followups'}.get(unquote(parts.fragment), parts.fragment)
            return urlunsplit(('', '', self.file_map[target], parts.query, fragment))
        if target.suffix.lower() in {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'}:
            return data_uri(target)
        if image:
            raise ValueError(f'Unsupported image type: {target.suffix}')
        return urlunsplit(('', '', quote(os.path.relpath(target, self.output_dir)), parts.query, parts.fragment))

    def link_open(self, renderer, tokens, idx, options, env):
        token = tokens[idx]
        original_url = token.attrGet('href') or ''
        token.attrSet('href', self.resolve_url(original_url))
        if token.attrGet('href').startswith('data:image/'):
            token.attrSet('download', Path(unquote(urlsplit(original_url).path)).name)
        if token.attrGet('href').startswith(('http://', 'https://')):
            token.attrSet('target', '_blank')
            token.attrSet('rel', 'noopener noreferrer')
        return renderer.renderToken(tokens, idx, options, env)

    def image(self, renderer, tokens, idx, options, env):
        token = tokens[idx]
        self.images += 1
        token.attrSet('src', self.resolve_url(token.attrGet('src') or '', image=True))
        token.attrSet('alt', renderer.renderInlineAsText(token.children or [], options, env))
        token.attrSet('loading', 'lazy')
        image = renderer.renderToken(tokens, idx, options, env)
        return '<button type="button" class="media-trigger" data-image-preview aria-label="放大查看图片">' + image + '<span class="media-trigger-label">放大查看 ↗</span></button>'

    def heading_open(self, renderer, tokens, idx, options, env):
        label = plain(tokens[idx + 1].content).lower()
        slug = ''.join(c for c in label if c.isalnum() or c in ' _-').replace(' ', '-')
        identifier = slug or 'section'
        serial = 1
        while identifier in self.heading_ids:
            identifier = f'{slug}-{serial}'
            serial += 1
        self.heading_ids.add(identifier)
        tokens[idx].attrSet('id', identifier)
        return renderer.renderToken(tokens, idx, options, env)

    def fence(self, renderer, tokens, idx, options, env):
        token = tokens[idx]
        language = token.info.strip().split(' ', 1)[0]
        self.code_blocks += 1
        if language == 'mermaid':
            uri, key, width, height = self.diagrams.render(token.content)
            return f'<figure class="diagram" data-diagram-sha256="{key}"><button type="button" class="media-trigger" data-image-preview aria-label="放大查看流程图"><img src="{uri}" alt="原文流程图" loading="lazy" width="{width:g}" height="{height:g}"><span class="media-trigger-label">放大查看流程图 ↗</span></button></figure>\n'
        return f'<pre tabindex="0" aria-label="{escape(language or "文本", quote=True)}代码或示意图"><code class="language-{escape(language or "text", quote=True)}">{escape(token.content)}</code></pre>\n'

    def render(self, text):
        return self.md.render(text)

    def inline(self, text):
        return self.md.renderInline(text)


def fill_template(template, values):
    def substitute(match):
        key = match[1]
        if key not in values:
            raise ValueError(f'Unknown template placeholder: {key}')
        return values[key]
    return re.sub(r'\{\{([a-z_]+)\}\}', substitute, template)


def render_question(question, file_map, output_dir, diagrams, shared):
    renderer = ContentRenderer(question, file_map, output_dir, diagrams)
    entry = question.entry
    title = entry['title']
    title_html = escape(title)
    title_html = re.sub(r'^([A-Za-z][A-Za-z0-9-]*)', r'<em>\1</em>', title_html, count=1)
    normalize = lambda text: re.sub(r'[\W_]+', '', text).lower()
    prompt = '' if normalize(plain(question.prompt)) == normalize(title) else '<div class="question-context prose">' + renderer.render(question.prompt) + '</div>'
    answers = []
    for answer in question.answers:
        meta = answer.metadata
        kind = 'AI 参考答案' if meta.get('type') == 'ai' else '参考答案'
        author = str(meta.get('author', '原文作者'))
        date = str(meta.get('updated') or meta.get('answered') or question.metadata['updated'])
        header = f'<p class="answer-source"><span class="source-badge">{kind}</span><span>{escape(author)}</span><span>{escape(date)}</span></p>'
        if len(question.answers) > 1:
            header = f'<h3 class="answer-author">答案 · {escape(author)}</h3>' + header
        answers.append('<section class="answer-version">' + header + '<div class="prose">' + renderer.render(answer.body) + '</div></section>')
    extras = []
    for heading, content in question.extras:
        css = ' references-prose' if heading == '参考' else ''
        extras.append(f'<section class="supplementary-section"><h3>{escape(heading)}</h3><div class="prose{css}">{renderer.render(content)}</div></section>')
    followups = []
    for index, item in enumerate(question.followups, 1):
        response = renderer.render(item.answer) if item.answer else '<p class="missing-response">原文暂未提供追答。</p>'
        followups.append(f'''<article class="followup" aria-labelledby="followup-{index}">
          <div class="followup-label">追问 {index:02d}</div><h3 id="followup-{index}">{renderer.inline(item.title)}</h3>
          <details class="followup-answer"><summary><span data-followup-label>展开追答</span><span class="sr-only">：{escape(plain(item.title))}</span><svg class="icon chevron" aria-hidden="true"><use href="#i-chevron"/></svg></summary><div class="followup-response"><div class="response-label">追答</div><div class="prose">{response}</div></div></details>
        </article>''')
    if followups:
        followup_html = '<section class="followups" id="followups" aria-labelledby="followups-title"><div class="followups-heading"><h2 id="followups-title">追问</h2><p>每个追答均可单独展开。</p></div>' + '\n'.join(followups) + '</section>'
    else:
        followup_html = ''
    supplement_file = TEMPLATES / 'supplements' / f'{entry["id"]}.html'
    supplement_js = supplement_file.with_suffix('.js')
    supplement = supplement_file.read_text() if supplement_file.exists() else ''
    supplement_script = '<script>\n' + supplement_js.read_text() + '\n</script>' if supplement_js.exists() else ''
    page_data = json.dumps({'questionId': entry['id'], 'language': entry.get('language', 'zh')}, ensure_ascii=False).replace('<', '\\u003c')
    values = {
        'language': 'zh-CN' if entry.get('language') == 'zh' else escape(entry.get('language', 'zh-CN')),
        'description': escape('先独立回答，再展开参考答案与追答。' + title, quote=True),
        'title': escape(title), 'title_html': title_html,
        'title_class': 'long-title' if len(title) > 42 else '',
        'question_id': escape(entry['id'].upper()),
        'category': escape(entry['category_label']),
        'difficulty': DIFFICULTIES[entry['difficulty']], 'role': ROLES[entry['role']],
        'question_context': prompt, 'answers': '\n'.join(answers), 'extras': '\n'.join(extras),
        'followups': followup_html, 'supplement': supplement, 'supplement_script': supplement_script,
        'source_file': escape(str(question.path.relative_to(ROOT))), 'source_hash': question.source_hash,
        'source_url': escape(os.path.relpath(question.path, output_dir), quote=True),
        'page_data': page_data, **shared,
    }
    result = fill_template((TEMPLATES / 'question.html').read_text(), values)
    return result, {'id': entry['id'], 'file': question.output_name,
                    'source': str(question.path.relative_to(ROOT)), 'source_sha256': question.source_hash,
                    'answers': len(question.answers), 'followups': len(question.followups),
                    'missing_followup_answers': sum(not f.answer for f in question.followups),
                    'code_blocks': renderer.code_blocks, 'images': renderer.images}


def render_index(questions, registry):
    workspace = ROOT / 'templates' / 'workspace'
    presentation = {
        'llm': ('模型基础', '原理 · 推理 · 模型选择', '#597eb6', '#e7effa'),
        'agent': ('Agent 架构', '工具 · 记忆 · 编排', '#6075c9', '#e9edfc'),
        'rag': ('RAG 检索', '检索 · 知识 · 生成', '#548779', '#e5f1ed'),
        'engineering': ('工程化', '可靠性 · 性能 · 成本', '#8c769f', '#eeeaf5'),
        'product': ('AI 产品', '需求 · 体验 · 落地', '#a38551', '#f6efdf'),
    }
    categories = []
    for item in sorted(registry, key=lambda category: category['sort']):
        short, description, color, wash = presentation.get(item['id'], (item['label'], '', '#6075c9', '#e9edfc'))
        categories.append({**item, 'short': short, 'description': description, 'color': color, 'wash': wash,
                           'count': sum(q.entry['category'] == item['id'] for q in questions)})
    catalog = [{key: q.entry.get(key, 'zh' if key == 'language' else []) for key in
                ['id', 'title', 'category', 'difficulty', 'role', 'tags', 'updated', 'language']}
               | {'file': q.output_name} for q in questions]
    category_navigation = ''.join(
        f'<a href="#questions?category={escape(c["id"])}" data-category-nav="{escape(c["id"])}"><span class="category-dot" style="--category-color:{c["color"]}"></span><span>{escape(c["short"])}</span><span class="nav-count">{c["count"]}</span></a>'
        for c in categories)
    sidebar = fill_template((workspace / 'sidebar.html').read_text(), {
        'total': str(len(questions)), 'category_navigation': category_navigation,
        'brand_icon': (ROOT / 'templates/brand.svg').read_text()})
    fallback = '<ul>' + ''.join(f'<li><a href="{escape(q.output_name)}">{escape(q.entry["title"])}</a></li>' for q in questions) + '</ul>'
    values = {
        'total': str(len(questions)), 'category_count': str(len(categories)),
        'css': (workspace / 'workspace.css').read_text(),
        'icons': (workspace / 'icons.svg').read_text(),
        'favicon': data_uri(ROOT / 'templates/brand.svg'),
        'script': (workspace / 'workspace.js').read_text(),
        'sidebar': sidebar, 'category_options': ''.join(f'<option value="{escape(c["id"])}">{escape(c["short"])}</option>' for c in categories),
        'catalog_json': json.dumps({'questions': catalog, 'categories': categories}, ensure_ascii=False).replace('<', '\\u003c'),
        'fallback_directory': fallback,
    }
    return fill_template((workspace / 'index.html').read_text(), values)


def load_questions():
    index = json.loads((ROOT / 'index.json').read_text())
    entries = index['questions']
    indexed = {item['file'] for item in entries}
    sources = {p.name for p in (ROOT / 'questions').glob('*.md')}
    if indexed != sources:
        raise ValueError(f'Index/source mismatch: {indexed ^ sources}')
    if len(indexed) != len(entries):
        raise ValueError('Duplicate source files in index')
    questions = []
    for entry in sorted(entries, key=lambda item: item['id']):
        if Path(entry['file']).name != entry['file'] or not entry['file'].endswith('.md'):
            raise ValueError('Invalid source filename')
        try:
            questions.append(parse_question(ROOT / 'questions' / entry['file'], entry))
        except Exception as error:
            raise ValueError(f'{entry["file"]}: {error}') from error
    return questions, index['categories']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check generated files without rewriting them')
    parser.add_argument('--audit', action='store_true', help='Validate and summarize source parsing only')
    parser.add_argument('--output', type=Path, default=ROOT / 'html')
    args = parser.parse_args()
    questions, registry = load_questions()
    if args.audit:
        print(json.dumps({'questions': len(questions), 'answers': sum(len(q.answers) for q in questions),
                          'followups': sum(len(q.followups) for q in questions),
                          'missing_followup_answers': sum(not f.answer for q in questions for f in q.followups)}, ensure_ascii=False))
        return
    output_dir = args.output.resolve()
    diagrams = DiagramRenderer(check=args.check)
    shared = {'css': (TEMPLATES / 'question.css').read_text(),
              'script': (TEMPLATES / 'question.js').read_text(),
              'icons': (TEMPLATES / 'icons.svg').read_text(),
              'favicon': data_uri(ROOT / 'templates/brand.svg')}
    file_map = {q.path.resolve(): q.output_name for q in questions}
    outputs = {}
    manifest = []
    for question in questions:
        output, record = render_question(question, file_map, output_dir, diagrams, shared)
        outputs[question.output_name] = output
        manifest.append(record)
    outputs['index.html'] = render_index(questions, registry)
    outputs['manifest.json'] = json.dumps({'schema_version': 1, 'generator': 'scripts/gen_html.py', 'questions': manifest}, ensure_ascii=False, indent=2) + '\n'
    stale = {p.name for p in output_dir.glob('*.html')} - outputs.keys()
    if stale:
        raise ValueError(f'Unexpected HTML files in output directory: {sorted(stale)}')
    changed = [name for name, content in outputs.items() if not (output_dir / name).exists() or (output_dir / name).read_text() != content]
    if args.check:
        if changed:
            raise ValueError(f'Generated files are out of date: {changed[:10]}')
        print(f'PASS: {len(questions)} question pages and index match sources/templates.')
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in changed:
        (output_dir / name).write_text(outputs[name], encoding='utf-8')
    print(f'Generated {len(questions)} question pages and index in {output_dir}; {len(changed)} files updated.')
    print(f'Follow-ups: {sum(r["followups"] for r in manifest)}; without source answers: {sum(r["missing_followup_answers"] for r in manifest)}; static diagrams: {len(diagrams.used)}.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        print(f'HTML generation failed: {error}', file=sys.stderr)
        sys.exit(1)

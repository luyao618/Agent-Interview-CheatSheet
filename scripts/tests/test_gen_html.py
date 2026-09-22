"""Behavior and content-preservation checks for the static question exporter."""
from collections import Counter
from hashlib import sha256
from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from urllib.parse import unquote, urlsplit

SCRIPT = Path(__file__).resolve().parents[1] / 'gen_html.py'
spec = importlib.util.spec_from_file_location('gen_html', SCRIPT)
g = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = g
spec.loader.exec_module(g)


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = []
        self.links = []
        self.images = []
        self.codes = []
        self.pre = 0
        self.code = None
        self.open_details = 0
        self.diagrams = 0
        self.tables = 0
        self.scripts = []
        self.script = None
        self.text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'a':
            self.links.append(attrs.get('href', ''))
        if tag == 'img':
            self.images.append(attrs.get('src', ''))
        if tag == 'details' and 'open' in attrs:
            self.open_details += 1
        if tag == 'figure' and 'data-diagram-sha256' in attrs:
            self.diagrams += 1
        if tag == 'table':
            self.tables += 1
        if tag == 'pre':
            self.pre += 1
        if tag == 'code' and self.pre:
            self.code = []
        if tag == 'script':
            self.script = [attrs, []]

    def handle_endtag(self, tag):
        if tag == 'code' and self.code is not None:
            self.codes.append(''.join(self.code))
            self.code = None
        if tag == 'pre':
            self.pre -= 1
        if tag == 'script' and self.script:
            self.scripts.append((self.script[0], ''.join(self.script[1])))
            self.script = None

    def handle_data(self, data):
        if self.code is not None:
            self.code.append(data)
        if self.script is not None:
            self.script[1].append(data)
        else:
            self.text.append(data)


class ParserTests(unittest.TestCase):
    def test_followup_styles_and_missing_answer(self):
        source = '''**追问 1：什么是回放？**

保留输入、输出与版本。

- **工具失败后重试吗？** 先检查预算。
- **追问三：副作用怎么处理？** 使用幂等与状态核验。
- 没有提供追答的问题？
'''
        follows, intro = g.split_followups(source)
        self.assertEqual(intro, '')
        self.assertEqual([f.title for f in follows], ['什么是回放？', '工具失败后重试吗？', '副作用怎么处理？', '没有提供追答的问题？'])
        self.assertEqual(follows[0].answer, '保留输入、输出与版本。')
        self.assertEqual(follows[2].answer, '使用幂等与状态核验。')
        self.assertEqual(follows[3].answer, '')

    def test_fences_do_not_become_sections_or_followups(self):
        source = '''**追问：如何解析示例？**

```markdown
## 答案
**追问：这只是代码？**
不要提取这一行。
```

仍属于第一个追答。

**追问：下一题？** 后续回答。
'''
        follows, _ = g.split_followups(source)
        self.assertEqual(len(follows), 2)
        self.assertIn('**追问：这只是代码？**', follows[0].answer)
        self.assertIn('仍属于第一个追答。', follows[0].answer)

    def test_only_explicit_followups_leave_mixed_answer(self):
        source = '''### 常见误区与追问

- **“工具调用就是循环？”** 这条是误区。
- **追问：如何停止？** 执行预算检查。

相关题仍是答案的一部分。
'''
        rest, follows = g.extract_embedded_followups(source)
        self.assertIn('这条是误区。', rest)
        self.assertIn('相关题仍是答案的一部分。', rest)
        self.assertNotIn('执行预算检查', rest)
        self.assertEqual(follows[0].answer, '执行预算检查。')

    def test_html_examples_are_inert_and_disclosures_preserved(self):
        source = '<details open onclick="bad()"><summary>示例</summary><script>bad()</script></details>'
        rendered = g.safe_raw(source)
        self.assertIn('<details><summary>示例</summary>', rendered)
        self.assertNotIn('onclick=', rendered)
        self.assertNotIn('<script>', rendered)
        self.assertIn('&lt;script&gt;', rendered)

    def test_multiple_authors_and_fenced_fake_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'agent-9999-test.md'
            path.write_text('''---
id: agent-9999
title: 测试问题
updated: 2026-09-21
answers:
  - author: A
    type: ai
  - author: B
    type: human
---
## 问题
测试问题
## 答案 · A
```text
## 问题
```
A 的答案。
## 答案 · B
B 的答案。
## 参考
参考资料。
''')
            q = g.parse_question(path, {'id': 'agent-9999', 'title': '测试问题', 'answers_count': 2})
            self.assertEqual(len(q.answers), 2)
            self.assertEqual(q.answers[1].metadata['author'], 'B')
            self.assertIn('## 问题', q.answers[0].body)
            self.assertEqual(q.extras, [('参考', '参考资料。')])


class CorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.questions, _ = g.load_questions()
        cls.output = g.ROOT / 'html'
        cls.pages = {}
        for path in cls.output.glob('*.html'):
            page = Page()
            page.feed(path.read_text())
            cls.pages[path.name] = page

    def test_every_indexed_question_has_one_page(self):
        self.assertEqual(len(self.questions), len(json.loads((g.ROOT / 'index.json').read_text())['questions']))
        self.assertEqual(set(self.pages), {q.output_name for q in self.questions} | {'index.html'})

    def test_all_pages_start_collapsed_and_have_unique_ids(self):
        for q in self.questions:
            with self.subTest(question=q.entry['id']):
                page = self.pages[q.output_name]
                self.assertEqual(page.open_details, 0)
                self.assertEqual(len(page.ids), len(set(page.ids)))
                self.assertIn('my-answer', page.ids)
                self.assertIn('reference-answer', page.ids)
                data = next(text for attrs, text in page.scripts if attrs.get('id') == 'page-data')
                self.assertEqual(json.loads(data)['questionId'], q.entry['id'])

    def test_local_links_and_assets_are_portable(self):
        for filename, page in self.pages.items():
            with self.subTest(file=filename):
                self.assertTrue(all(src.startswith('data:image/') for src in page.images))
                self.assertFalse(any('src' in attrs for attrs, _ in page.scripts))
                for link in page.links:
                    parts = urlsplit(link)
                    if parts.scheme or parts.netloc:
                        continue
                    target = (self.output / unquote(parts.path)).resolve() if parts.path else self.output / filename
                    self.assertTrue(target.exists(), link)
                    if parts.fragment and target.name in self.pages:
                        fragment = unquote(parts.fragment)
                        if target.name == 'index.html' and fragment.startswith('questions?'):
                            self.assertIn('questions', self.pages[target.name].ids)
                            self.assertRegex(fragment, r'^questions\?(?:category=[a-z]+|difficulty=(?:easy|medium|hard))$')
                        else:
                            self.assertIn(fragment, self.pages[target.name].ids, link)

    def test_workspace_catalog_matches_every_question(self):
        page = self.pages['index.html']
        payload = next(text for attrs, text in page.scripts if attrs.get('id') == 'workspace-data')
        catalog = json.loads(payload)
        entries = {item['id']: item for item in catalog['questions']}
        self.assertEqual(set(entries), {q.entry['id'] for q in self.questions})
        for question in self.questions:
            entry = entries[question.entry['id']]
            self.assertEqual(entry['file'], question.output_name)
            for field in ['title', 'category', 'difficulty', 'role']:
                self.assertEqual(entry[field], question.entry[field])
        self.assertEqual(sum(c['count'] for c in catalog['categories']), len(self.questions))
        self.assertEqual(len(page.ids), len(set(page.ids)))
        for route in ['home', 'questions', 'answers', 'reader']:
            self.assertIn(route, page.ids)

    def test_source_code_tables_and_diagrams_are_not_lost(self):
        for q in self.questions:
            with self.subTest(question=q.entry['id']):
                raw = q.path.read_text().split('---', 2)[2]
                tokens = g.PARSER.parse(raw)
                source_code = [t.content for t in tokens if t.type in {'fence', 'code_block'} and t.info.strip() != 'mermaid']
                page = self.pages[q.output_name]
                digest = lambda blocks: Counter(sha256(block.encode()).hexdigest() for block in blocks)
                self.assertEqual(digest(source_code), digest(page.codes), 'Code blocks changed or disappeared')
                self.assertEqual(sum(t.type == 'table_open' for t in tokens), page.tables)
                self.assertEqual(sum(t.type == 'fence' and t.info.strip() == 'mermaid' for t in tokens), page.diagrams)

    def test_manifest_matches_the_sources_and_followups(self):
        manifest = json.loads((self.output / 'manifest.json').read_text())
        records = {item['id']: item for item in manifest['questions']}
        for q in self.questions:
            record = records[q.entry['id']]
            self.assertEqual(record['source_sha256'], sha256(q.path.read_bytes()).hexdigest())
            self.assertEqual(record['followups'], len(q.followups))
            page = self.pages[q.output_name]
            self.assertEqual(sum(i.startswith('followup-') for i in page.ids), len(q.followups))
            text = ''.join(page.text)
            self.assertEqual(text.count('原文暂未提供追答。'), sum(not f.answer for f in q.followups))


if __name__ == '__main__':
    unittest.main()

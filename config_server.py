import os
import yaml
from flask import Flask, request, redirect, render_template_string

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCES_PATH = os.path.join(BASE_DIR, "config", "sources.yaml")

app = Flask(__name__)


HTML = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>AI 投资情报 Agent - 来源配置</title>
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 40px;
      background: #f7f8fa;
      color: #111827;
    }
    h1 {
      margin-bottom: 8px;
    }
    .desc {
      color: #6b7280;
      margin-bottom: 24px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      background: white;
      margin-bottom: 32px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }
    th, td {
      border-bottom: 1px solid #e5e7eb;
      padding: 10px;
      text-align: left;
      font-size: 14px;
    }
    th {
      background: #f3f4f6;
    }
    input, select {
      width: 100%;
      padding: 8px;
      box-sizing: border-box;
      border: 1px solid #d1d5db;
      border-radius: 6px;
    }
    button {
      padding: 8px 14px;
      border: none;
      border-radius: 6px;
      background: #2563eb;
      color: white;
      cursor: pointer;
    }
    button.delete {
      background: #dc2626;
    }
    .card {
      background: white;
      padding: 20px;
      border-radius: 10px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.08);
      margin-bottom: 24px;
    }
    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr 2fr 1fr;
      gap: 12px;
      margin-bottom: 12px;
    }
    .path {
      font-size: 13px;
      color: #6b7280;
      background: #eef2ff;
      padding: 8px 10px;
      border-radius: 6px;
      display: inline-block;
      margin-bottom: 20px;
    }
  </style>
</head>
<body>
  <h1>AI 投资情报 Agent - 来源配置</h1>
  <div class="desc">这里配置 Agent 每天要读取的信息源。保存后会写入 sources.yaml。</div>
  <div class="path">配置文件：{{ sources_path }}</div>

  <div class="card">
    <h2>新增来源</h2>
    <form method="post" action="/add">
      <div class="grid">
        <input name="company" placeholder="公司，如 NVIDIA" required>

        <select name="layer" required>
          <option value="energy">能源层 energy</option>
          <option value="chips">芯片/计算层 chips</option>
          <option value="infrastructure">基础设施层 infrastructure</option>
          <option value="models">模型层 models</option>
          <option value="applications">应用层 applications</option>
          <option value="capital">资本层 capital</option>
        </select>

        <select name="type" required>
          <option value="web">网页 web</option>
          <option value="rss">RSS rss</option>
        </select>

        <input name="url" placeholder="https://example.com" required>

        <select name="priority" required>
          <option value="high">高 high</option>
          <option value="medium">中 medium</option>
          <option value="low">低 low</option>
        </select>
      </div>
      <button type="submit">新增来源</button>
    </form>
  </div>

  <div class="card">
    <h2>当前来源</h2>
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>公司</th>
          <th>层级</th>
          <th>类型</th>
          <th>URL</th>
          <th>优先级</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        {% for source in sources %}
        <tr>
          <td>{{ loop.index }}</td>
          <td>{{ source.company }}</td>
          <td>{{ source.layer }}</td>
          <td>{{ source.type }}</td>
          <td>{{ source.url }}</td>
          <td>{{ source.priority }}</td>
          <td>
            <form method="post" action="/delete/{{ loop.index0 }}">
              <button class="delete" type="submit">删除</button>
            </form>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</body>
</html>
"""


def load_sources():
    if not os.path.exists(SOURCES_PATH):
        return []

    with open(SOURCES_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return data.get("sources", [])


def save_sources(sources):
    data = {
        "sources": sources
    }

    with open(SOURCES_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


@app.route("/")
def index():
    sources = load_sources()
    return render_template_string(
        HTML,
        sources=sources,
        sources_path=SOURCES_PATH
    )


@app.route("/add", methods=["POST"])
def add_source():
    sources = load_sources()

    new_source = {
        "company": request.form.get("company", "").strip(),
        "layer": request.form.get("layer", "").strip(),
        "type": request.form.get("type", "").strip(),
        "url": request.form.get("url", "").strip(),
        "priority": request.form.get("priority", "").strip(),
    }

    sources.append(new_source)
    save_sources(sources)

    return redirect("/")


@app.route("/delete/<int:index>", methods=["POST"])
def delete_source(index):
    sources = load_sources()

    if 0 <= index < len(sources):
        sources.pop(index)
        save_sources(sources)

    return redirect("/")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True)

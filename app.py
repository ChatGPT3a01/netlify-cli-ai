#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Netlify AI Deploy Studio - 智慧部署助手 (IDE 風格版本)
曾慶良(阿亮老師)建置

啟動方式：python app.py
網址：http://127.0.0.1:5886
"""

import os
import sys
import json
import subprocess
import webbrowser
import threading
import requests
from pathlib import Path
from typing import Optional, Dict, List, Any
from flask import Flask, render_template, request, jsonify
import time

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
app.config['TEMPLATES_AUTO_RELOAD'] = True  # 關閉模板緩存

# ============================================================================
# 專案分析器
# ============================================================================

class ProjectAnalyzer:
    """專案分析器 - 自動偵測專案類型和結構"""

    def __init__(self, project_path: str):
        self.path = Path(project_path).resolve()
        self.files: List[str] = []
        self.analysis: Dict[str, Any] = {}

    def scan_files(self) -> List[str]:
        """掃描專案檔案"""
        self.files = []
        ignore_dirs = {'.git', 'node_modules', '__pycache__', '.netlify', 'venv', '.venv'}

        for root, dirs, files in os.walk(self.path):
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), self.path)
                self.files.append(rel_path)

        return self.files

    def detect_project_type(self) -> Dict[str, Any]:
        """偵測專案類型"""
        self.scan_files()

        analysis = {
            'type': 'static',
            'type_name': '靜態網站',
            'has_html': False,
            'has_python': False,
            'has_node': False,
            'has_netlify_config': False,
            'has_env_file': False,
            'has_env_example': False,
            'has_gitignore': False,
            'has_requirements': False,
            'has_package_json': False,
            'python_files': [],
            'env_vars_needed': [],
            'publish_dir': '.',
            'functions_dir': None,
            'build_command': None,
            'file_count': len(self.files),
            'path': str(self.path),
        }

        for file in self.files:
            file_lower = file.lower()

            if file_lower.endswith('.html'):
                analysis['has_html'] = True

            if file_lower.endswith('.py'):
                analysis['has_python'] = True
                analysis['python_files'].append(file)

            if file_lower == 'package.json':
                analysis['has_node'] = True
                analysis['has_package_json'] = True

            if file_lower == 'netlify.toml':
                analysis['has_netlify_config'] = True

            if file_lower == '.env':
                analysis['has_env_file'] = True

            if file_lower == '.env.example':
                analysis['has_env_example'] = True

            if file_lower == '.gitignore':
                analysis['has_gitignore'] = True

            if file_lower == 'requirements.txt':
                analysis['has_requirements'] = True

        # 判斷專案類型
        if analysis['has_python']:
            for py_file in analysis['python_files']:
                if 'functions' in py_file.lower() or 'netlify' in py_file.lower():
                    analysis['type'] = 'python-functions'
                    analysis['type_name'] = 'Python Serverless Functions'
                    parts = Path(py_file).parts
                    for i, part in enumerate(parts):
                        if 'functions' in part.lower():
                            analysis['functions_dir'] = str(Path(*parts[:i+1]))
                            break
                    break

            if analysis['type'] == 'static' and analysis['has_python']:
                analysis['type'] = 'python-functions'
                analysis['type_name'] = 'Python Serverless Functions'

        if analysis['has_node'] and analysis['has_package_json']:
            analysis['type'] = 'node-project'
            analysis['type_name'] = 'Node.js 專案'
            analysis['build_command'] = 'npm run build'

        analysis['env_vars_needed'] = self._detect_env_vars()

        self.analysis = analysis
        return analysis

    def _detect_env_vars(self) -> List[str]:
        """偵測可能需要的環境變數"""
        env_vars = set()
        patterns = [
            ('OPENAI_API_KEY', ['openai', 'gpt', 'chatgpt']),
            ('GOOGLE_API_KEY', ['google', 'gemini', 'generativeai']),
            ('ANTHROPIC_API_KEY', ['anthropic', 'claude']),
            ('DATABASE_URL', ['database', 'postgres', 'mysql', 'mongodb']),
            ('SECRET_KEY', ['secret', 'jwt', 'session']),
        ]

        for file in self.files:
            if file.endswith(('.py', '.js', '.ts', '.jsx', '.tsx')):
                try:
                    file_path = self.path / file
                    content = file_path.read_text(encoding='utf-8', errors='ignore').lower()
                    for env_var, keywords in patterns:
                        if any(kw in content for kw in keywords):
                            env_vars.add(env_var)
                except Exception:
                    pass

        return list(env_vars)


# ============================================================================
# 配置生成器
# ============================================================================

class ConfigGenerator:
    """配置檔生成器"""

    @staticmethod
    def generate_netlify_toml(publish_dir: str = ".",
                               functions_dir: Optional[str] = None,
                               build_command: Optional[str] = None,
                               python_version: str = "3.10") -> str:
        lines = ['[build]']

        if functions_dir:
            lines.append(f'  functions = "{functions_dir}"')

        lines.append(f'  publish = "{publish_dir}"')

        if build_command:
            lines.append(f'  command = "{build_command}"')

        if functions_dir:
            lines.append('')
            lines.append('[build.environment]')
            lines.append(f'  PYTHON_VERSION = "{python_version}"')
            lines.append('')
            lines.append('[[redirects]]')
            lines.append('  from = "/api/*"')
            lines.append('  to = "/.netlify/functions/:splat"')
            lines.append('  status = 200')

        return '\n'.join(lines) + '\n'

    @staticmethod
    def generate_gitignore() -> str:
        return """# 環境變數（含敏感資訊）
.env
.env.local
.env.production

# Netlify 本地快取
.netlify/

# Python
__pycache__/
*.py[cod]
venv/
.venv/

# Node.js
node_modules/

# 系統檔案
.DS_Store
Thumbs.db

# IDE
.vscode/
.idea/
"""

    @staticmethod
    def generate_env_example(env_vars: List[str]) -> str:
        lines = ['# 環境變數範例', '# 複製此檔案為 .env 並填入真實的值', '']

        descriptions = {
            'OPENAI_API_KEY': '# OpenAI API Key - https://platform.openai.com/api-keys',
            'GOOGLE_API_KEY': '# Google API Key (Gemini) - https://aistudio.google.com/app/apikey',
            'ANTHROPIC_API_KEY': '# Anthropic API Key - https://console.anthropic.com/',
            'DATABASE_URL': '# 資料庫連線字串',
            'SECRET_KEY': '# 應用程式密鑰',
        }

        for var in env_vars:
            if var in descriptions:
                lines.append(descriptions[var])
            lines.append(f'{var}=your_{var.lower()}_here')
            lines.append('')

        lines.append('# 注意：永遠不要將 .env 檔案上傳到 Git！')
        return '\n'.join(lines)

    @staticmethod
    def generate_requirements(env_vars: List[str]) -> str:
        packages = []

        if 'OPENAI_API_KEY' in env_vars:
            packages.append('openai')
        if 'GOOGLE_API_KEY' in env_vars:
            packages.append('google-generativeai')
        if 'ANTHROPIC_API_KEY' in env_vars:
            packages.append('anthropic')

        if not packages:
            packages.append('# 在此加入你需要的 Python 套件')

        return '\n'.join(packages) + '\n'


# ============================================================================
# 部署器
# ============================================================================

class Deployer:
    """Netlify 部署器"""

    def __init__(self, project_path: str):
        self.path = Path(project_path).resolve()

    def check_netlify_cli(self) -> bool:
        try:
            # Windows 需要 shell=True 來找到 npm 全域安裝的命令
            result = subprocess.run('netlify --version', capture_output=True, text=True, shell=True)
            return result.returncode == 0
        except Exception:
            return False

    def check_logged_in(self) -> bool:
        try:
            result = subprocess.run('netlify status', capture_output=True, text=True, shell=True, cwd=str(self.path))
            return 'logged in' in result.stdout.lower()
        except Exception:
            return False

    def run_command(self, cmd: List[str]) -> Dict[str, Any]:
        try:
            # 將命令列表轉換為字串，並使用 shell=True
            cmd_str = ' '.join(cmd)
            result = subprocess.run(
                cmd_str,
                capture_output=True,
                shell=True,
                cwd=str(self.path),
                encoding='utf-8',
                errors='ignore'  # 忽略無法解碼的字元
            )
            return {
                'success': result.returncode == 0,
                'stdout': result.stdout or '',
                'stderr': result.stderr or ''
            }
        except Exception as e:
            return {'success': False, 'stdout': '', 'stderr': str(e)}


# ============================================================================
# AI 助手
# ============================================================================

class AIAssistant:
    """AI 助手 - 支援多個 AI 服務提供商"""

    SYSTEM_PROMPT = """你是 Netlify 部署專家助手。你的任務是：
1. 幫助用戶解決部署問題
2. 分析錯誤訊息並提供解決方案
3. 提供 Netlify 相關的最佳實踐建議
4. 回答關於網站部署的問題

請用繁體中文回答，保持簡潔明瞭。"""

    @staticmethod
    def chat_openai(api_key: str, message: str, context: str = None) -> Dict[str, Any]:
        """使用 OpenAI API"""
        try:
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }

            messages = [{'role': 'system', 'content': AIAssistant.SYSTEM_PROMPT}]

            if context:
                messages.append({'role': 'system', 'content': f'專案資訊：{context}'})

            messages.append({'role': 'user', 'content': message})

            response = requests.post(
                'https://api.openai.com/v1/chat/completions',
                headers=headers,
                json={
                    'model': 'gpt-4o-mini',
                    'messages': messages,
                    'max_tokens': 1000,
                    'temperature': 0.7
                },
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    'success': True,
                    'response': data['choices'][0]['message']['content']
                }
            else:
                return {
                    'success': False,
                    'error': f'API 錯誤: {response.status_code} - {response.text}'
                }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @staticmethod
    def chat_anthropic(api_key: str, message: str, context: str = None) -> Dict[str, Any]:
        """使用 Anthropic API"""
        try:
            headers = {
                'x-api-key': api_key,
                'Content-Type': 'application/json',
                'anthropic-version': '2023-06-01'
            }

            system = AIAssistant.SYSTEM_PROMPT
            if context:
                system += f'\n\n專案資訊：{context}'

            response = requests.post(
                'https://api.anthropic.com/v1/messages',
                headers=headers,
                json={
                    'model': 'claude-3-haiku-20240307',
                    'max_tokens': 1000,
                    'system': system,
                    'messages': [{'role': 'user', 'content': message}]
                },
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    'success': True,
                    'response': data['content'][0]['text']
                }
            else:
                return {
                    'success': False,
                    'error': f'API 錯誤: {response.status_code} - {response.text}'
                }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @staticmethod
    def chat_google(api_key: str, message: str, context: str = None) -> Dict[str, Any]:
        """使用 Google Gemini API"""
        try:
            prompt = AIAssistant.SYSTEM_PROMPT + '\n\n'
            if context:
                prompt += f'專案資訊：{context}\n\n'
            prompt += f'用戶問題：{message}'

            response = requests.post(
                f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}',
                headers={'Content-Type': 'application/json'},
                json={
                    'contents': [{'parts': [{'text': prompt}]}],
                    'generationConfig': {
                        'maxOutputTokens': 1000,
                        'temperature': 0.7
                    }
                },
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                text = data['candidates'][0]['content']['parts'][0]['text']
                return {'success': True, 'response': text}
            else:
                return {
                    'success': False,
                    'error': f'API 錯誤: {response.status_code} - {response.text}'
                }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @staticmethod
    def test_connection(provider: str, api_key: str) -> Dict[str, Any]:
        """測試 API 連線"""
        test_message = "請回覆 OK"

        if provider == 'openai':
            result = AIAssistant.chat_openai(api_key, test_message)
        elif provider == 'anthropic':
            result = AIAssistant.chat_anthropic(api_key, test_message)
        elif provider == 'google':
            result = AIAssistant.chat_google(api_key, test_message)
        else:
            return {'success': False, 'error': '不支援的 AI 服務提供商'}

        return result


# ============================================================================
# Flask 路由
# ============================================================================

@app.route('/')
def index():
    """首頁"""
    return render_template('index.html')


@app.route('/api/browse-folder', methods=['GET'])
def browse_folder():
    """開啟資料夾選擇對話框"""
    try:
        import tkinter as tk
        from tkinter import filedialog

        # 建立隱藏的 Tk 視窗
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)

        # 開啟資料夾選擇對話框
        folder_path = filedialog.askdirectory(
            title="選擇專案資料夾",
            mustexist=True
        )

        root.destroy()

        if folder_path:
            return jsonify({'success': True, 'path': folder_path})
        else:
            return jsonify({'success': False, 'error': '未選擇資料夾'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/analyze', methods=['POST'])
def analyze_project():
    """分析專案"""
    data = request.json
    project_path = data.get('path', '.')

    path = Path(project_path).resolve()
    if not path.exists():
        return jsonify({'success': False, 'error': f'路徑不存在: {path}'})
    if not path.is_dir():
        return jsonify({'success': False, 'error': f'這不是資料夾: {path}'})

    try:
        analyzer = ProjectAnalyzer(str(path))
        analysis = analyzer.detect_project_type()
        return jsonify({
            'success': True,
            'analysis': analysis,
            'file_tree': analyzer.files  # 回傳檔案列表給前端
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/read-file', methods=['POST'])
def read_file():
    """讀取檔案內容"""
    data = request.json
    project_path = data.get('path')
    filename = data.get('filename')

    if not project_path or not filename:
        return jsonify({'success': False, 'error': '缺少參數'})

    try:
        # 在專案目錄中尋找檔案
        base_path = Path(project_path).resolve()
        file_path = None

        # 先嘗試直接路徑
        direct_path = base_path / filename
        if direct_path.exists():
            file_path = direct_path
        else:
            # 搜尋檔案
            for root, dirs, files in os.walk(base_path):
                # 排除特定目錄
                dirs[:] = [d for d in dirs if d not in {'.git', 'node_modules', '__pycache__', '.netlify', 'venv', '.venv'}]
                if filename in files:
                    file_path = Path(root) / filename
                    break

        if not file_path or not file_path.exists():
            return jsonify({'success': False, 'error': f'找不到檔案: {filename}'})

        # 檢查是否為文字檔
        try:
            content = file_path.read_text(encoding='utf-8')
            return jsonify({'success': True, 'content': content})
        except UnicodeDecodeError:
            return jsonify({'success': False, 'error': '無法讀取二進位檔案'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/generate', methods=['POST'])
def generate_configs():
    """生成配置檔"""
    data = request.json
    project_path = data.get('path')
    config = data.get('config', {})

    path = Path(project_path).resolve()
    results = []

    try:
        # 生成 netlify.toml
        if config.get('netlify_toml', True):
            content = ConfigGenerator.generate_netlify_toml(
                publish_dir=config.get('publish_dir', '.'),
                functions_dir=config.get('functions_dir'),
                build_command=config.get('build_command')
            )
            (path / 'netlify.toml').write_text(content, encoding='utf-8')
            results.append({'file': 'netlify.toml', 'success': True})

        # 生成 .gitignore
        if config.get('gitignore', True):
            content = ConfigGenerator.generate_gitignore()
            (path / '.gitignore').write_text(content, encoding='utf-8')
            results.append({'file': '.gitignore', 'success': True})

        # 生成 .env.example
        env_vars = config.get('env_vars', [])
        if config.get('env_example', True) and env_vars:
            content = ConfigGenerator.generate_env_example(env_vars)
            (path / '.env.example').write_text(content, encoding='utf-8')
            results.append({'file': '.env.example', 'success': True})

        # 生成 requirements.txt
        functions_dir = config.get('functions_dir')
        if config.get('requirements', True) and functions_dir:
            content = ConfigGenerator.generate_requirements(env_vars)
            func_path = path / functions_dir
            func_path.mkdir(parents=True, exist_ok=True)
            (func_path / 'requirements.txt').write_text(content, encoding='utf-8')
            results.append({'file': f'{functions_dir}/requirements.txt', 'success': True})

        return jsonify({'success': True, 'results': results})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/list-teams', methods=['GET'])
def list_teams():
    """列出所有團隊"""
    try:
        deployer = Deployer('.')
        result = deployer.run_command(['netlify', 'teams:list', '--json'])

        if result['stdout']:
            try:
                teams_data = json.loads(result['stdout'])
                teams = []
                for team in teams_data:
                    teams.append({
                        'name': team.get('name', 'Unknown'),
                        'slug': team.get('slug', ''),
                        'id': team.get('id', '')
                    })
                return jsonify({'success': True, 'teams': teams})
            except json.JSONDecodeError:
                return jsonify({'success': False, 'error': '解析失敗', 'teams': []})

        return jsonify({'success': False, 'error': '無法取得團隊列表', 'teams': []})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'teams': []})


@app.route('/api/list-sites', methods=['GET'])
def list_sites():
    """列出所有站點"""
    try:
        deployer = Deployer('.')
        result = deployer.run_command(['netlify', 'sites:list', '--json'])

        if result['stdout']:
            import json
            try:
                sites_data = json.loads(result['stdout'])
                sites = []
                for site in sites_data[:10]:  # 最多顯示 10 個
                    sites.append({
                        'name': site.get('name', 'Unknown'),
                        'url': site.get('ssl_url') or site.get('url') or f"https://{site.get('name', '')}.netlify.app",
                        'updated': site.get('updated_at', '')[:10] if site.get('updated_at') else ''
                    })
                return jsonify({'success': True, 'sites': sites})
            except json.JSONDecodeError:
                return jsonify({'success': False, 'error': '解析失敗', 'sites': []})

        return jsonify({'success': False, 'error': '無法取得站點列表', 'sites': []})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'sites': []})


@app.route('/api/check-cli', methods=['GET'])
def check_cli():
    """檢查 Netlify CLI 狀態"""
    deployer = Deployer('.')
    cli_installed = deployer.check_netlify_cli()
    logged_in = deployer.check_logged_in() if cli_installed else False

    return jsonify({
        'cli_installed': cli_installed,
        'logged_in': logged_in
    })


@app.route('/api/login', methods=['POST'])
def netlify_login():
    """執行 Netlify 登錄"""
    deployer = Deployer('.')

    # 先檢查是否已經登錄
    if deployer.check_logged_in():
        return jsonify({
            'success': True,
            'message': '您已經登錄 Netlify',
            'stdout': '已登錄'
        })

    # 執行 netlify login 命令
    # 注意：這會開啟瀏覽器讓用戶授權
    result = deployer.run_command(['netlify', 'login'])

    # 檢查是否登錄成功
    all_output = result['stdout'] + result['stderr']
    login_success = 'Logged in' in all_output or 'logged in' in all_output.lower() or 'Successfully' in all_output

    if login_success or result['success']:
        return jsonify({
            'success': True,
            'message': '登錄成功',
            'stdout': result['stdout'],
            'stderr': result['stderr']
        })
    else:
        return jsonify({
            'success': False,
            'message': '登錄失敗或已取消',
            'stdout': result['stdout'],
            'stderr': result['stderr']
        })


@app.route('/api/init-site', methods=['POST'])
def init_site():
    """初始化/連結 Netlify 站點"""
    data = request.json
    project_path = data.get('path')
    site_name = data.get('site_name', '')
    account_slug = data.get('account_slug', '')  # 團隊 slug

    deployer = Deployer(project_path)

    # 先檢查是否已連結
    result = deployer.run_command(['netlify', 'status'])
    if 'Current site' in result['stdout']:
        return jsonify({
            'success': True,
            'message': '站點已連結',
            'stdout': result['stdout']
        })

    # 創建新站點 - 使用 --account-slug 避免互動式提問
    cmd = ['netlify', 'sites:create']
    if site_name:
        cmd.extend(['--name', site_name])
    if account_slug:
        cmd.extend(['--account-slug', account_slug])

    result = deployer.run_command(cmd)

    # 檢查是否真的創建成功（忽略 Node.js 警告）
    all_output = result['stdout'] + result['stderr']
    site_created = 'Project Created' in all_output or 'Site Created' in all_output or 'Linked to' in all_output

    if not site_created and not result['success']:
        return jsonify({
            'success': False,
            'error': '創建站點失敗',
            'stderr': result['stderr']
        })

    return jsonify({
        'success': True,
        'message': '站點創建並連結成功！',
        'stdout': result['stdout'],
        'stderr': result['stderr']
    })


@app.route('/api/update-domain', methods=['POST'])
def update_domain():
    """更新站點域名"""
    data = request.json
    project_path = data.get('path')
    new_name = data.get('new_name', '')

    if not new_name:
        return jsonify({'success': False, 'error': '請輸入新的站點名稱'})

    deployer = Deployer(project_path)

    # 使用 Netlify CLI 更新站點名稱
    result = deployer.run_command(['netlify', 'sites:update', '--name', new_name])

    if result['success'] or 'Site updated' in result['stdout']:
        return jsonify({
            'success': True,
            'message': f'域名已更新為 {new_name}.netlify.app',
            'stdout': result['stdout']
        })
    else:
        return jsonify({
            'success': False,
            'error': '更新失敗',
            'stderr': result['stderr']
        })


@app.route('/api/deploy', methods=['POST'])
def deploy():
    """執行部署"""
    data = request.json
    project_path = data.get('path')
    deploy_type = data.get('type', 'preview')

    deployer = Deployer(project_path)

    # 直接嘗試部署，不做預先檢查
    if deploy_type == 'preview':
        result = deployer.run_command(['netlify', 'deploy'])
    else:
        result = deployer.run_command(['netlify', 'deploy', '--prod'])

    # 合併 stdout 和 stderr 來尋找 URL（有時候輸出在 stderr）
    all_output = result['stdout'] + '\n' + result['stderr']

    # 嘗試從輸出中提取 URL
    url = None
    deploy_url = None

    for line in all_output.split('\n'):
        line_lower = line.lower()
        # 尋找各種可能的 URL 格式
        if 'website' in line_lower and 'url' in line_lower:
            parts = line.split()
            if parts:
                url = parts[-1]
        elif 'deploy' in line_lower and 'url' in line_lower:
            parts = line.split()
            if parts:
                deploy_url = parts[-1]
        elif 'https://' in line and 'netlify' in line:
            # 直接提取 netlify URL
            import re
            urls = re.findall(r'https://[^\s]+netlify[^\s]*', line)
            if urls:
                url = urls[0]

    # 如果找到 URL，即使有警告也算成功
    final_url = url or deploy_url

    # 判斷是否真的失敗（排除警告）
    is_success = result['success'] or (final_url is not None)

    # 過濾掉不重要的警告
    stderr = result['stderr']
    if 'unsettled top-level await' in stderr and final_url:
        # 這只是 Node.js 警告，不是真正的錯誤
        is_success = True

    return jsonify({
        'success': is_success,
        'url': final_url,
        'stdout': result['stdout'],
        'stderr': stderr
    })


@app.route('/api/run-command', methods=['POST'])
def run_command():
    """執行 Netlify 命令"""
    data = request.json
    project_path = data.get('path', '.')
    command = data.get('command', [])

    if not command:
        return jsonify({'success': False, 'error': '沒有指定命令'})

    deployer = Deployer(project_path)
    result = deployer.run_command(command)

    return jsonify(result)


@app.route('/api/chat', methods=['POST'])
def chat():
    """AI 聊天"""
    data = request.json
    message = data.get('message', '')
    provider = data.get('provider', 'openai')
    api_key = data.get('api_key', '')
    context = data.get('context')

    if not message:
        return jsonify({'success': False, 'error': '請輸入訊息'})

    if not api_key:
        return jsonify({'success': False, 'error': '請先設定 API Key'})

    if provider == 'openai':
        result = AIAssistant.chat_openai(api_key, message, context)
    elif provider == 'anthropic':
        result = AIAssistant.chat_anthropic(api_key, message, context)
    elif provider == 'google':
        result = AIAssistant.chat_google(api_key, message, context)
    else:
        return jsonify({'success': False, 'error': '不支援的 AI 服務'})

    return jsonify(result)


@app.route('/api/test-connection', methods=['POST'])
def test_connection():
    """測試 API 連線"""
    data = request.json
    provider = data.get('provider', 'openai')
    api_key = data.get('api_key', '')

    if not api_key:
        return jsonify({'success': False, 'error': '請輸入 API Key'})

    result = AIAssistant.test_connection(provider, api_key)
    return jsonify(result)


# ============================================================================
# 主程式
# ============================================================================

def open_browser():
    """延遲開啟瀏覽器"""
    time.sleep(1.5)
    webbrowser.open('http://127.0.0.1:5886')


if __name__ == '__main__':
    print("=" * 60)
    print("  Netlify AI Deploy Studio v2.0")
    print("  智慧部署助手 - IDE 風格介面")
    print("  曾慶良(阿亮老師)建置")
    print("=" * 60)
    print()
    print("  啟動中...")
    print("  網址: http://127.0.0.1:5886")
    print()
    print("  按 Ctrl+C 可停止伺服器")
    print("=" * 60)

    # 自動開啟瀏覽器
    threading.Thread(target=open_browser, daemon=True).start()

    # 啟動 Flask
    app.run(host='127.0.0.1', port=5886, debug=False)
